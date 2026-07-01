"""CRUD operations for all database models."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.models import User, Dataset, FairnessAudit, MLModel, Report, AuditLog


# ---- Users ----
async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()

async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, email: str, username: str, hashed_password: str,
                      full_name: str = "", role: str = "analyst", institution: str = "") -> User:
    user = User(email=email, username=username, hashed_password=hashed_password,
                full_name=full_name, role=role, institution=institution)
    db.add(user)
    await db.flush()
    return user

async def update_user_login(db: AsyncSession, user_id: str) -> None:
    await db.execute(update(User).where(User.id == user_id).values(last_login=datetime.utcnow()))

async def list_users(db: AsyncSession) -> List[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


# ---- Datasets ----
async def create_dataset(db: AsyncSession, file_id: str, filename: str,
                         original_filename: str, file_size: int,
                         owner_id: Optional[str] = None,
                         storage_ref: Optional[str] = None) -> Dataset:
    ds = Dataset(file_id=file_id, filename=filename, original_filename=original_filename,
                 file_size=file_size, owner_id=owner_id, storage_ref=storage_ref)
    db.add(ds)
    await db.flush()
    return ds

async def get_dataset_by_file_id(db: AsyncSession, file_id: str) -> Optional[Dataset]:
    result = await db.execute(select(Dataset).where(Dataset.file_id == file_id))
    return result.scalar_one_or_none()

async def update_dataset_status(db: AsyncSession, file_id: str, status: str, **kwargs) -> None:
    values = {"status": status, **kwargs}
    if status == "completed":
        values["processed_at"] = datetime.utcnow()
    await db.execute(update(Dataset).where(Dataset.file_id == file_id).values(**values))

async def list_datasets(db: AsyncSession, owner_id: Optional[str] = None) -> List[Dataset]:
    q = select(Dataset).order_by(Dataset.uploaded_at.desc())
    if owner_id:
        q = q.where(Dataset.owner_id == owner_id)
    result = await db.execute(q)
    return list(result.scalars().all())


# ---- Fairness Audits ----
async def create_fairness_audit(db: AsyncSession, dataset_db_id: str, data: dict) -> FairnessAudit:
    audit = FairnessAudit(dataset_id=dataset_db_id, **data)
    db.add(audit)
    await db.flush()
    return audit

async def list_fairness_audits(db: AsyncSession, dataset_id: Optional[str] = None) -> List[FairnessAudit]:
    q = select(FairnessAudit).order_by(FairnessAudit.created_at.desc())
    if dataset_id:
        q = q.where(FairnessAudit.dataset_id == dataset_id)
    result = await db.execute(q)
    return list(result.scalars().all())


# ---- ML Models ----
async def upsert_ml_model(db: AsyncSession, data: dict) -> MLModel:
    existing = await db.execute(select(MLModel).where(MLModel.dataset_id == data.get("dataset_id")))
    model = existing.scalar_one_or_none()
    if model:
        for k, v in data.items():
            setattr(model, k, v)
    else:
        model = MLModel(**data)
        db.add(model)
    await db.flush()
    return model


# ---- Reports ----
async def create_report(db: AsyncSession, data: dict) -> Report:
    report = Report(**data)
    db.add(report)
    await db.flush()
    return report

async def list_reports(db: AsyncSession, dataset_id: Optional[str] = None) -> List[Report]:
    q = select(Report).order_by(Report.created_at.desc())
    if dataset_id:
        q = q.where(Report.dataset_id == dataset_id)
    result = await db.execute(q)
    return list(result.scalars().all())


# ---- Audit Log ----
async def log_action(db: AsyncSession, action: str, user_id: Optional[str] = None,
                     resource_type: Optional[str] = None, resource_id: Optional[str] = None,
                     details: Optional[dict] = None, ip_address: Optional[str] = None) -> None:
    entry = AuditLog(user_id=user_id, action=action, resource_type=resource_type,
                     resource_id=resource_id, details=details, ip_address=ip_address)
    db.add(entry)
    await db.flush()


# ---- User API Keys ----
from backend.database.models import UserAPIKey

async def save_user_api_key(db: AsyncSession, user_id: str, provider: str,
                             encrypted_key: str, active_model: Optional[str] = None) -> UserAPIKey:
    """Upsert an API key for a user+provider."""
    result = await db.execute(
        select(UserAPIKey).where(UserAPIKey.user_id == user_id, UserAPIKey.provider == provider)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.encrypted_key = encrypted_key
        existing.active_model = active_model
        existing.updated_at = datetime.utcnow()
        existing.is_active = True
    else:
        existing = UserAPIKey(user_id=user_id, provider=provider,
                              encrypted_key=encrypted_key, active_model=active_model)
        db.add(existing)
    await db.flush()
    return existing

async def get_user_api_keys(db: AsyncSession, user_id: str) -> List[UserAPIKey]:
    """Return all active API keys for a user."""
    result = await db.execute(
        select(UserAPIKey).where(UserAPIKey.user_id == user_id, UserAPIKey.is_active == True)
    )
    return list(result.scalars().all())

async def delete_user_api_key(db: AsyncSession, user_id: str, provider: str) -> None:
    """Soft-delete (deactivate) a user's API key for a provider."""
    await db.execute(
        update(UserAPIKey)
        .where(UserAPIKey.user_id == user_id, UserAPIKey.provider == provider)
        .values(is_active=False)
    )
