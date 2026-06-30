"""Report generation Celery tasks."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    name="backend.workers.tasks.report_tasks.generate_report",
    bind=True,
    time_limit=300,
)
def generate_report(
    self,
    dataset_id: str,
    file_path: str,
    report_type: str,
    output_path: str,
    field_map: Optional[Dict] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a PDF report asynchronously."""
    try:
        import pandas as pd
        from backend.core.report_generator import ReportGenerator
        from backend.core.fairness_engine import FairnessEngine

        ext = file_path.rsplit(".", 1)[-1].lower()
        df = pd.read_csv(file_path) if ext == "csv" else pd.read_excel(file_path)

        rg = ReportGenerator()
        fe = FairnessEngine()

        if report_type == "fairness":
            audit = fe.run_audit(df, field_map or {})
            pdf_bytes = rg.generate_fairness_report(audit, df)
        elif report_type == "compliance":
            audit = fe.run_audit(df, field_map or {})
            pdf_bytes = rg.generate_compliance_report(audit, df)
        elif report_type == "risk":
            pdf_bytes = rg.generate_risk_report(df)
        else:
            audit = fe.run_audit(df, field_map or {})
            pdf_bytes = rg.generate_executive_summary(audit, df)

        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

        _save_report_record(dataset_id, report_type, output_path, len(pdf_bytes), user_id)

        logger.info(f"Report '{report_type}' generated: {output_path} ({len(pdf_bytes)} bytes)")
        return {"status": "completed", "path": output_path, "size": len(pdf_bytes)}

    except Exception as exc:
        logger.exception(f"Report generation failed: {exc}")
        raise self.retry(exc=exc)


def _save_report_record(dataset_id: str, report_type: str, file_path: str, file_size: int, user_id: Optional[str]) -> None:
    """Persist report metadata to DB."""
    try:
        import asyncio
        from backend.database.connection import AsyncSessionLocal
        from backend.database.models import Report

        async def _do():
            async with AsyncSessionLocal() as db:
                # Find dataset pk from file_id
                from sqlalchemy import select
                from backend.database.models import Dataset
                row = await db.execute(select(Dataset).where(Dataset.file_id == dataset_id))
                dataset = row.scalar_one_or_none()
                if dataset:
                    report = Report(
                        dataset_id=dataset.id,
                        report_type=report_type,
                        format="pdf",
                        file_path=file_path,
                        file_size=file_size,
                        generated_by_id=user_id,
                    )
                    db.add(report)
                    await db.commit()

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_do())
        loop.close()
    except Exception as e:
        logger.warning(f"Could not save report record: {e}")
