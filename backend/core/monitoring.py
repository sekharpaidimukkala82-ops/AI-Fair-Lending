"""
Monitoring Engine – tracks platform usage, fairness trends, and detects data drift.
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple

from backend.config import Config
from backend.models.schemas import MonitoringAlert


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

class _QueryRecord:
    __slots__ = ("session_id", "query", "response_time", "timestamp")

    def __init__(self, session_id: str, query: str, response_time: float) -> None:
        self.session_id    = session_id
        self.query         = query
        self.response_time = response_time
        self.timestamp     = datetime.utcnow()


class _FairnessRecord:
    __slots__ = ("score", "dataset_id", "timestamp")

    def __init__(self, score: float, dataset_id: str) -> None:
        self.score      = score
        self.dataset_id = dataset_id
        self.timestamp  = datetime.utcnow()


# ---------------------------------------------------------------------------
# Monitoring Engine
# ---------------------------------------------------------------------------

class MonitoringEngine:
    """
    In-memory monitoring store for queries, fairness scores, and drift detection.
    """

    _MAX_QUERIES  = 10_000
    _MAX_FAIRNESS = 1_000

    def __init__(self) -> None:
        self._queries:   Deque[_QueryRecord]   = deque(maxlen=self._MAX_QUERIES)
        self._fairness:  Deque[_FairnessRecord] = deque(maxlen=self._MAX_FAIRNESS)
        self._alerts:    List[MonitoringAlert]  = []
        self._dataset_stats: Dict[str, Dict[str, Any]] = {}

        # Per-hour query counter: key = "YYYY-MM-DD HH"
        self._hourly_counts: Dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_query(
        self,
        session_id: str,
        query: str,
        response_time: float,
    ) -> None:
        """Record a RAG query event."""
        rec = _QueryRecord(session_id, query, response_time)
        self._queries.append(rec)
        hour_key = rec.timestamp.strftime("%Y-%m-%d %H")
        self._hourly_counts[hour_key] += 1

        # Alert on slow response
        if response_time > 10.0:
            self._add_alert(
                alert_type="performance",
                severity="warning",
                message=f"Slow query response: {response_time:.1f}s",
                details={"session_id": session_id, "response_time": response_time},
            )

    def record_fairness_score(
        self,
        score: float,
        dataset_id: str,
    ) -> None:
        """Record a fairness audit result."""
        rec = _FairnessRecord(score, dataset_id)
        self._fairness.append(rec)

        if score < 60.0:
            self._add_alert(
                alert_type="bias",
                severity="critical",
                message=f"Critical fairness score: {score:.1f}/100 for dataset {dataset_id}",
                details={"dataset_id": dataset_id, "score": score},
            )
        elif score < 80.0:
            self._add_alert(
                alert_type="bias",
                severity="warning",
                message=f"Fairness score below threshold: {score:.1f}/100 for dataset {dataset_id}",
                details={"dataset_id": dataset_id, "score": score},
            )

    def record_dataset_stats(
        self,
        dataset_id: str,
        stats: Dict[str, Any],
    ) -> None:
        """Store dataset-level statistics for drift comparison."""
        self._dataset_stats[dataset_id] = {
            **stats,
            "recorded_at": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Drift Detection
    # ------------------------------------------------------------------

    def detect_drift(
        self,
        baseline_stats: Dict[str, Any],
        current_stats: Dict[str, Any],
    ) -> List[MonitoringAlert]:
        """
        Compare baseline and current dataset statistics.
        Returns alerts for columns where mean or rate shifts exceed the threshold.
        """
        threshold = Config.DRIFT_THRESHOLD
        alerts: List[MonitoringAlert] = []

        for key in baseline_stats:
            if key not in current_stats:
                continue
            try:
                base_val = float(baseline_stats[key])
                curr_val = float(current_stats[key])
                if base_val == 0:
                    continue
                drift_pct = abs(curr_val - base_val) / abs(base_val)
                if drift_pct > threshold:
                    alert = self._add_alert(
                        alert_type="drift",
                        severity="warning" if drift_pct < 0.30 else "critical",
                        message=f"Data drift detected in '{key}': {drift_pct:.1%} change",
                        details={
                            "feature": key,
                            "baseline": base_val,
                            "current": curr_val,
                            "drift_pct": round(drift_pct, 4),
                        },
                    )
                    alerts.append(alert)
            except (TypeError, ValueError):
                continue

        return alerts

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Return aggregated metrics for the monitoring dashboard."""
        total_queries = len(self._queries)

        # Average response time
        avg_rt = 0.0
        if self._queries:
            avg_rt = sum(q.response_time for q in self._queries) / total_queries

        # Average fairness score
        avg_fair: Optional[float] = None
        if self._fairness:
            avg_fair = round(
                sum(f.score for f in self._fairness) / len(self._fairness), 2
            )

        # Recent fairness trend (last 20 records)
        fair_trend = [
            {
                "timestamp": f.timestamp.isoformat(),
                "score": f.score,
                "dataset_id": f.dataset_id,
            }
            for f in list(self._fairness)[-20:]
        ]

        # Query volume by hour (last 24 h)
        now = datetime.utcnow()
        volume_by_hour: Dict[str, int] = {}
        for h in range(24):
            ts = now - timedelta(hours=h)
            key = ts.strftime("%Y-%m-%d %H")
            volume_by_hour[key] = self._hourly_counts.get(key, 0)

        # Recent alerts (unresolved first)
        recent_alerts = sorted(
            self._alerts[-50:],
            key=lambda a: (a.resolved, a.timestamp),
            reverse=False,
        )[-20:]

        return {
            "total_queries": total_queries,
            "total_datasets": len(self._dataset_stats),
            "average_fairness_score": avg_fair,
            "average_response_time_seconds": round(avg_rt, 3),
            "recent_alerts": [a.model_dump() for a in recent_alerts],
            "query_volume_by_hour": volume_by_hour,
            "fairness_score_trend": fair_trend,
            "dataset_stats": self._dataset_stats,
            "system_status": self._system_status(),
            "unresolved_alerts": sum(1 for a in self._alerts if not a.resolved),
        }

    def check_alerts(self) -> List[MonitoringAlert]:
        """Return all unresolved alerts."""
        return [a for a in self._alerts if not a.resolved]

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark an alert as resolved. Returns True if found."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                return True
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> MonitoringAlert:
        alert = MonitoringAlert(
            alert_id=str(uuid.uuid4()),
            alert_type=alert_type,
            severity=severity,
            message=message,
            details=details or {},
        )
        self._alerts.append(alert)
        # Keep last 500 alerts
        if len(self._alerts) > 500:
            self._alerts = self._alerts[-500:]
        return alert

    def _system_status(self) -> str:
        unresolved_critical = sum(
            1 for a in self._alerts if not a.resolved and a.severity == "critical"
        )
        if unresolved_critical > 0:
            return "critical"
        unresolved_warning = sum(
            1 for a in self._alerts if not a.resolved and a.severity == "warning"
        )
        if unresolved_warning > 3:
            return "degraded"
        return "healthy"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_monitoring_engine: Optional[MonitoringEngine] = None


def get_monitoring_engine() -> MonitoringEngine:
    global _monitoring_engine
    if _monitoring_engine is None:
        _monitoring_engine = MonitoringEngine()
    return _monitoring_engine
