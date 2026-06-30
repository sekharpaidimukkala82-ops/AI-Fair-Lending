"""
AI Provider – unified interface for Google Gemini, OpenAI, and Groq.
API keys stored in memory only — never written to disk.

Groq is FREE with generous limits: https://console.groq.com/keys
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("fair_lending.ai_provider")

# ---------------------------------------------------------------------------
# In-memory runtime key store
# ---------------------------------------------------------------------------
_runtime_keys: Dict[str, str] = {}
_active_provider: str = "gemini"
_active_model: str = ""

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
]

OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
]

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]

DEFAULT_MODELS = {
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "groq":   "llama-3.3-70b-versatile",
}

# Deprecated model names → replacement
DEPRECATED_MODELS = {
    "gemini-pro":      "gemini-2.0-flash",
    "gemini-1.0-pro":  "gemini-2.0-flash",
}


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def set_api_key(provider: str, api_key: str) -> None:
    _runtime_keys[provider.lower()] = api_key.strip()
    logger.info(f"API key updated: {provider}")


def set_active_provider(provider: str, model: str = "") -> None:
    global _active_provider, _active_model
    _active_provider = provider.lower()
    _active_model    = model
    logger.info(f"Active provider: {_active_provider} / {model or 'default'}")


def get_api_key(provider: str) -> str:
    provider = provider.lower()
    if provider in _runtime_keys and _runtime_keys[provider]:
        return _runtime_keys[provider]
    env_map = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "groq":   "GROQ_API_KEY",
    }
    return os.getenv(env_map.get(provider, ""), "")


def get_active_provider() -> str:
    return _active_provider


def get_active_model() -> str:
    if _active_model:
        return DEPRECATED_MODELS.get(_active_model, _active_model)
    return DEFAULT_MODELS.get(_active_provider, "llama-3.3-70b-versatile")


def get_status() -> Dict[str, Any]:
    gemini_key = get_api_key("gemini")
    openai_key = get_api_key("openai")
    groq_key   = get_api_key("groq")
    return {
        "active_provider": _active_provider,
        "active_model":    get_active_model(),
        "gemini_configured": bool(gemini_key),
        "openai_configured": bool(openai_key),
        "groq_configured":   bool(groq_key),
        "gemini_key_source": "runtime" if _runtime_keys.get("gemini") else ("env" if gemini_key else "none"),
        "openai_key_source": "runtime" if _runtime_keys.get("openai") else ("env" if openai_key else "none"),
        "groq_key_source":   "runtime" if _runtime_keys.get("groq")   else ("env" if groq_key   else "none"),
        "available_gemini_models": GEMINI_MODELS,
        "available_openai_models": OPENAI_MODELS,
        "available_groq_models":   GROQ_MODELS,
    }


# ---------------------------------------------------------------------------
# Unified call
# ---------------------------------------------------------------------------

def call_llm(
    prompt: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    prov = (provider or _active_provider).lower()
    mdl  = DEPRECATED_MODELS.get(model or "", model or "") or get_active_model()
    key  = get_api_key(prov)

    if not key:
        hints = {
            "gemini": "Get a free key at aistudio.google.com/app/apikey",
            "openai": "Get a key at platform.openai.com/api-keys (requires billing)",
            "groq":   "Get a FREE key at console.groq.com/keys — no billing required!",
        }
        hint = hints.get(prov, "")
        raise ValueError(
            f"{prov.capitalize()} API key not configured. "
            f"Add it in AI Settings (gear icon). {hint}"
        )

    if prov == "gemini":
        return _call_gemini(prompt, key, mdl, temperature, max_tokens)
    elif prov == "openai":
        return _call_openai(prompt, key, mdl, temperature, max_tokens)
    elif prov == "groq":
        return _call_groq(prompt, key, mdl, temperature, max_tokens)
    else:
        raise ValueError(f"Unknown provider '{prov}'. Use: gemini, openai, groq")


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str, api_key: str, model: str, temperature: float, max_tokens: int) -> str:
    model_name = DEPRECATED_MODELS.get(model, model) or "gemini-2.0-flash"
    models_to_try = [model_name] + [m for m in ["gemini-2.0-flash", "gemini-1.5-flash"] if m != model_name]

    last_error = None
    for try_model in models_to_try:
        try:
            try:
                from google import genai as new_genai
                client = new_genai.Client(api_key=api_key)
                response = client.models.generate_content(model=try_model, contents=prompt)
                return response.text.strip()
            except (ImportError, AttributeError):
                pass

            import google.generativeai as genai
            genai.configure(api_key=api_key)
            try:
                cfg = genai.GenerationConfig(temperature=temperature, max_output_tokens=max_tokens)
            except AttributeError:
                cfg = genai.types.GenerationConfig(temperature=temperature, max_output_tokens=max_tokens)
            m = genai.GenerativeModel(model_name=try_model, generation_config=cfg)
            return m.generate_content(prompt).text.strip()

        except Exception as e:
            last_error = e
            err_str = str(e)
            if "RESOURCE_EXHAUSTED" in err_str or ("429" in err_str and "quota" in err_str.lower()):
                raise ValueError(
                    "Gemini quota exceeded (limit: 0 — billing not enabled or free tier exhausted). "
                    "Fix: Enable billing at console.cloud.google.com/billing, "
                    "OR switch to Groq (FREE) in AI Settings."
                )
            if ("404" in err_str or "not found" in err_str.lower()) and len(models_to_try) > 1:
                logger.warning(f"Model '{try_model}' unavailable, trying next...")
                continue
            break

    raise ValueError(f"Gemini error: {last_error}")


def _call_openai(prompt: str, api_key: str, model: str, temperature: float, max_tokens: int) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except ImportError:
        raise ValueError("openai package not installed. Run: pip install openai")
    except Exception as e:
        err_str = str(e)
        if "insufficient_quota" in err_str or "429" in err_str:
            raise ValueError(
                "OpenAI quota exceeded. Add billing credits at platform.openai.com/billing, "
                "OR switch to Groq (FREE) in AI Settings."
            )
        raise ValueError(f"OpenAI error: {e}")


def _call_groq(prompt: str, api_key: str, model: str, temperature: float, max_tokens: int) -> str:
    """
    Groq provides FREE inference for open-source models (LLaMA, Mixtral, Gemma).
    Get a free API key at https://console.groq.com/keys — no billing required.
    """
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model or "llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except ImportError:
        # Fall back to OpenAI-compatible API (Groq uses OpenAI SDK format)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
            response = client.chat.completions.create(
                model=model or "llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except ImportError:
            raise ValueError("Install groq or openai package: pip install groq")
    except Exception as e:
        raise ValueError(f"Groq error: {e}")
