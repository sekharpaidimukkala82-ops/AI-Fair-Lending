"""
Data Lineage Tracker — Priority 3 Enterprise Feature.

Records every transformation applied to a dataset:
who cleaned it, what rules were applied, version history.
Required for regulatory examination (OCC/FDIC/Fed).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("fair_lending.lineage")


class LineageTracker:
    """
    Records data transformation steps to the data_lineage table.
    Can be used as a context manager or called directly.

    Usage:
        tracker = LineageTracker()
        await tracker.record(dataset_id, "Schema Discovery", "schema",
                             operator="SchemaDiscovery", input_rows=5000, output_rows=5000,
                             parameters={"mapped_columns": 12})
    """

    async def record(
        self,
        dataset_file_id: str,
        step_name: str,
        step_type: str,
        operator: Optional[str] = None,
        input_rows: Optional[int] = None,
        output_rows: Optional[int] = None,
        parameters: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Persist a lineage step to the database."""
        try:
            from backend.database.connection import AsyncSessionLocal
            from backend.database.models import DataLineage, Dataset
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                # Resolve file_id → dataset.id
                row = await db.execute(select(Dataset).where(Dataset.file_id == dataset_file_id))
                dataset = row.scalar_one_or_none()
                if not dataset:
                    logger.warning(f"Lineage: dataset {dataset_file_id} not found in DB")
                    return

                entry = DataLineage(
                    dataset_id=dataset.id,
                    step_name=step_name,
                    step_type=step_type,
                    operator=operator,
                    input_rows=input_rows,
                    output_rows=output_rows,
                    parameters=parameters,
                    notes=notes,
                )
                db.add(entry)
                await db.commit()
                logger.debug(f"Lineage recorded: {step_name} for dataset {dataset_file_id}")

        except Exception as e:
            logger.warning(f"Lineage record failed (non-fatal): {e}")

    def record_sync(self, dataset_file_id: str, step_name: str, step_type: str, **kwargs) -> None:
        """Synchronous wrapper for use inside Celery tasks."""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.record(dataset_file_id, step_name, step_type, **kwargs))
        finally:
            loop.close()

    async def get_lineage(self, dataset_file_id: str) -> List[Dict[str, Any]]:
        """Retrieve full lineage history for a dataset."""
        try:
            from backend.database.connection import AsyncSessionLocal
            from backend.database.models import DataLineage, Dataset
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                row = await db.execute(select(Dataset).where(Dataset.file_id == dataset_file_id))
                dataset = row.scalar_one_or_none()
                if not dataset:
                    return []

                rows = await db.execute(
                    select(DataLineage)
                    .where(DataLineage.dataset_id == dataset.id)
                    .order_by(DataLineage.created_at.asc())
                )
                entries = rows.scalars().all()
                return [
                    {
                        "id": e.id,
                        "step_name": e.step_name,
                        "step_type": e.step_type,
                        "operator": e.operator,
                        "input_rows": e.input_rows,
                        "output_rows": e.output_rows,
                        "parameters": e.parameters,
                        "notes": e.notes,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in entries
                ]
        except Exception as e:
            logger.warning(f"Lineage fetch failed: {e}")
            return []


# Singleton
_tracker = LineageTracker()


def get_lineage_tracker() -> LineageTracker:
    return _tracker
