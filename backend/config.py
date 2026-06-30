"""
Configuration module for Fair Lending Intelligence Platform.
Loads environment variables and provides a central Config class.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the project root or backend directory
load_dotenv()


class Config:
    # -------------------------------------------------------------------------
    # AI / External API
    # -------------------------------------------------------------------------
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # -------------------------------------------------------------------------
    # Storage Paths
    # -------------------------------------------------------------------------
    BASE_DIR: Path = Path(__file__).parent
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", str(BASE_DIR / "chroma_db"))
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))
    MODELS_DIR: str = os.getenv("MODELS_DIR", str(BASE_DIR / "models_store"))

    # -------------------------------------------------------------------------
    # Chunking
    # -------------------------------------------------------------------------
    CHUNK_SIZES: list[int] = [500, 750, 1000]
    DEFAULT_CHUNK_SIZE: int = 750
    CHUNK_OVERLAP: int = 100

    # -------------------------------------------------------------------------
    # Embeddings & Vector Store
    # -------------------------------------------------------------------------
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    COLLECTION_NAME: str = "lending_intelligence"

    # -------------------------------------------------------------------------
    # File Handling
    # -------------------------------------------------------------------------
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100 MB in bytes
    ALLOWED_EXTENSIONS: set[str] = {"csv", "xlsx", "json", "pdf", "txt", "docx"}

    # -------------------------------------------------------------------------
    # RAG / Chat
    # -------------------------------------------------------------------------
    MAX_CONTEXT_CHUNKS: int = 10
    SESSION_HISTORY_LIMIT: int = 20  # max messages per session stored in memory
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_TEMPERATURE: float = 0.2
    GEMINI_MAX_TOKENS: int = 2048

    # -------------------------------------------------------------------------
    # ML
    # -------------------------------------------------------------------------
    RANDOM_FOREST_ESTIMATORS: int = 200
    KMEANS_CLUSTERS: int = 5
    ANOMALY_CONTAMINATION: float = 0.05
    RISK_THRESHOLDS: dict = {
        "LOW": 0.75,       # probability >= 0.75 → LOW risk
        "MEDIUM": 0.50,    # probability >= 0.50 → MEDIUM risk
        "HIGH": 0.25,      # probability >= 0.25 → HIGH risk
        # below 0.25 → VERY_HIGH risk
    }

    # -------------------------------------------------------------------------
    # Fairness
    # -------------------------------------------------------------------------
    DISPARATE_IMPACT_THRESHOLD: float = 0.80  # 4/5ths rule

    # -------------------------------------------------------------------------
    # Monitoring
    # -------------------------------------------------------------------------
    DRIFT_THRESHOLD: float = 0.15  # 15% change triggers alert

    # -------------------------------------------------------------------------
    # Class Methods
    # -------------------------------------------------------------------------
    @classmethod
    def validate(cls) -> list[str]:
        """Return a list of validation warnings."""
        warnings: list[str] = []
        if not cls.GEMINI_API_KEY:
            warnings.append("GEMINI_API_KEY is not set – chat features will be unavailable.")
        return warnings

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create required directories if they don't exist."""
        for d in (cls.UPLOAD_DIR, cls.CHROMA_PERSIST_DIR, cls.MODELS_DIR):
            Path(d).mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_allowed_file(cls, filename: str) -> bool:
        """Return True if the file extension is in ALLOWED_EXTENSIONS."""
        if "." not in filename:
            return False
        ext = filename.rsplit(".", 1)[-1].lower()
        return ext in cls.ALLOWED_EXTENSIONS

    @classmethod
    def get_upload_path(cls, filename: str) -> Path:
        """Return the full path for an uploaded file."""
        return Path(cls.UPLOAD_DIR) / filename

    @classmethod
    def to_dict(cls) -> dict:
        """Return a sanitised config dict (no secrets)."""
        return {
            "chroma_persist_dir": cls.CHROMA_PERSIST_DIR,
            "upload_dir": cls.UPLOAD_DIR,
            "models_dir": cls.MODELS_DIR,
            "chunk_sizes": cls.CHUNK_SIZES,
            "default_chunk_size": cls.DEFAULT_CHUNK_SIZE,
            "embedding_model": cls.EMBEDDING_MODEL,
            "collection_name": cls.COLLECTION_NAME,
            "max_file_size_mb": cls.MAX_FILE_SIZE // (1024 * 1024),
            "allowed_extensions": list(cls.ALLOWED_EXTENSIONS),
            "gemini_model": cls.GEMINI_MODEL,
            "disparate_impact_threshold": cls.DISPARATE_IMPACT_THRESHOLD,
        }
