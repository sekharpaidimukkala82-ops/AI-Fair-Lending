"""
Utility helpers for the Fair Lending Intelligence Platform.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# ID / Hashing
# ---------------------------------------------------------------------------

def generate_id() -> str:
    """Return a new UUID4 string."""
    return str(uuid.uuid4())


def hash_content(content: Union[str, bytes]) -> str:
    """Return a SHA-256 hex digest of content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:16]


# ---------------------------------------------------------------------------
# DataFrame utilities
# ---------------------------------------------------------------------------

def df_to_records(df: pd.DataFrame, max_rows: Optional[int] = None) -> List[Dict[str, Any]]:
    """Convert a DataFrame to a list of JSON-safe dicts."""
    if max_rows is not None:
        df = df.head(max_rows)
    # Replace NaN/inf with None for JSON serialisation
    return json.loads(df.replace({np.nan: None, np.inf: None, -np.inf: None}).to_json(orient="records"))


def safe_numeric(value: Any, default: float = 0.0) -> float:
    """Convert a value to float, returning default on failure."""
    try:
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def normalise_column_name(name: str) -> str:
    """Lowercase, replace spaces and special chars with underscores."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower().strip()).strip("_")


def infer_id_column(df: pd.DataFrame) -> Optional[str]:
    """Heuristically find an applicant ID column."""
    for col in df.columns:
        lc = col.lower()
        if any(kw in lc for kw in ("applicant_id", "app_id", "loan_number", "case_id", "record_id")):
            return col
    # Fall back to first column that looks like an ID (all-unique values)
    for col in df.columns:
        if df[col].nunique() == len(df):
            return col
    return None


def compute_column_stats(series: pd.Series) -> Dict[str, Any]:
    """Return a statistics dict for a pandas Series."""
    stats: Dict[str, Any] = {
        "dtype": str(series.dtype),
        "count": len(series),
        "missing": int(series.isna().sum()),
        "unique": int(series.nunique()),
    }
    if pd.api.types.is_numeric_dtype(series):
        desc = series.describe()
        stats.update({
            "min": round(float(desc["min"]), 4) if not np.isnan(desc["min"]) else None,
            "max": round(float(desc["max"]), 4) if not np.isnan(desc["max"]) else None,
            "mean": round(float(desc["mean"]), 4) if not np.isnan(desc["mean"]) else None,
            "std": round(float(desc["std"]), 4) if not np.isnan(desc["std"]) else None,
            "median": round(float(series.median()), 4),
        })
    else:
        mode = series.mode()
        stats["top_value"] = str(mode.iloc[0]) if len(mode) > 0 else None
        stats["top_values"] = series.value_counts().head(5).to_dict()
    return stats


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def truncate_text(text: str, max_chars: int = 500, suffix: str = "...") -> str:
    """Truncate text to max_chars, appending suffix if truncated."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)] + suffix


def clean_text(text: str) -> str:
    """Remove excessive whitespace and non-printable characters."""
    text = re.sub(r"[^\x20-\x7E\n\t]", "", text)  # remove non-ASCII control chars
    text = re.sub(r"\s{3,}", " ", text)  # collapse multiple spaces
    return text.strip()


def extract_numbers(text: str) -> List[float]:
    """Extract all numeric values from a string."""
    matches = re.findall(r"[-+]?\d*\.?\d+", text)
    return [float(m) for m in matches]


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------

def file_size_human(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"


def safe_file_path(base_dir: Union[str, Path], filename: str) -> Path:
    """
    Return a safe file path by prepending base_dir and stripping path traversal.
    Raises ValueError if the resolved path escapes base_dir.
    """
    base = Path(base_dir).resolve()
    target = (base / Path(filename).name).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError(f"Path traversal detected: {filename}")
    return target


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------

class SafeEncoder(json.JSONEncoder):
    """JSON encoder that handles pandas/numpy types and datetimes."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) else float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        return super().default(obj)


def to_json(obj: Any, indent: int = 2) -> str:
    """Serialise an object to JSON using SafeEncoder."""
    return json.dumps(obj, cls=SafeEncoder, indent=indent)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_probability(value: float, name: str = "value") -> float:
    """Ensure value is in [0, 1]."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1, got {value}")
    return value


def validate_score(value: float, name: str = "score", lo: float = 0, hi: float = 100) -> float:
    """Ensure value is in [lo, hi]."""
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}, got {value}")
    return value
