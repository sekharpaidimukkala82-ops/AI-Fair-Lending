"""
Sentry Integration — Priority 4 Observability.

Initializes Sentry SDK for error tracking with stack traces,
performance monitoring, and user context.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("fair_lending.sentry")


def init_sentry() -> bool:
    """
    Initialize Sentry SDK. Called once at startup.
    No-op if SENTRY_DSN is not set.
    Returns True if Sentry was successfully initialized.
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("SENTRY_DSN not set — error tracking disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration

        environment = os.getenv("ENVIRONMENT", "production")
        release = os.getenv("APP_VERSION", "2.0.0")

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=f"fair-lending@{release}",
            traces_sample_rate=0.1,        # 10% of requests for performance
            profiles_sample_rate=0.05,     # 5% for profiling
            send_default_pii=False,        # IMPORTANT: no PII in error reports
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                CeleryIntegration(),
                LoggingIntegration(
                    level=logging.WARNING,
                    event_level=logging.ERROR,
                ),
            ],
            before_send=_scrub_pii,
            ignore_errors=[
                KeyboardInterrupt,
                # Don't report 404s or auth failures as errors
            ],
        )
        logger.info(f"Sentry initialized: env={environment}, release={release}")
        return True

    except ImportError:
        logger.info("sentry-sdk not installed — error tracking disabled")
        return False
    except Exception as e:
        logger.warning(f"Sentry init failed: {e}")
        return False


def _scrub_pii(event: dict, hint: dict) -> dict:
    """
    Remove personally identifiable information before sending to Sentry.
    This is critical for financial data compliance.
    """
    SENSITIVE_KEYS = {
        "password", "hashed_password", "api_key", "secret_key",
        "access_token", "authorization", "ssn", "tax_id",
        "applicant_name", "borrower_name", "email", "phone",
        "address", "income", "credit_score", "account_number",
    }

    def _scrub(obj: object) -> object:
        if isinstance(obj, dict):
            return {
                k: "[REDACTED]" if k.lower() in SENSITIVE_KEYS else _scrub(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_scrub(item) for item in obj]
        return obj

    # Scrub request body
    if "request" in event and "data" in event.get("request", {}):
        event["request"]["data"] = _scrub(event["request"]["data"])

    # Scrub extra context
    if "extra" in event:
        event["extra"] = _scrub(event["extra"])

    return event


def set_user_context(user_id: str, username: str, role: str) -> None:
    """Set Sentry user context for the current request (no PII)."""
    try:
        import sentry_sdk
        sentry_sdk.set_user({"id": user_id, "username": username, "role": role})
    except Exception:
        pass


def capture_exception(exc: Exception, context: dict | None = None) -> None:
    """Manually capture an exception with optional context."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if context:
                for k, v in context.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass
