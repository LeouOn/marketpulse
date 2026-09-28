"""Yield-curve pipeline run status (T6).

Records the outcome of every pipeline run so the API can explain empty
responses ("pipeline has not run" / last error) instead of returning a
bare ``null``. File-based by design: the status is a small JSON file in
the pipeline's own (gitignored) cache directory, which keeps this inside
T6's file ownership -- no new DB table or migration.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

#: Keep the per-run log bounded.
_MAX_RUNS = 20


def default_status_path() -> Path:
    """Status file lives beside the pipeline's parquet cache."""
    from src.yield_curve.config import get_config

    return Path(get_config().cache_dir) / "status.json"


class PipelineStatusStore:
    """Atomic, append-only-ish JSON record of pipeline runs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record_run(
        self,
        *,
        ok: bool,
        saved: int = 0,
        snapshot_date=None,
        error: str | None = None,
    ) -> None:
        status = self.load() or {}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        runs = (status.get("runs") or [])[-(_MAX_RUNS - 1):]
        runs.append({"at": now, "ok": ok, "saved": saved, "error": error})
        status["runs"] = runs
        status["last_run_at"] = now
        if ok:
            status["last_success_at"] = now
            status["last_error"] = None
            status.pop("last_error_at", None)
            if snapshot_date is not None:
                status["last_snapshot_date"] = str(snapshot_date)
        else:
            status["last_error"] = error or "unknown error"
            status["last_error_at"] = now
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(status, indent=2))
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning(f"yield_curve status: cannot write {self.path}: {exc}")

    def load(self) -> dict | None:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            logger.warning(f"yield_curve status: cannot read {self.path}: {exc}")
            return None
