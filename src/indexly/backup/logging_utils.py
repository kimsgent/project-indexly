from pathlib import Path
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

# ==============================
# Log schema constants
# ==============================
LOG_SCHEMA = "indexly.log"
LOG_SCHEMA_VERSION = 1

# ==============================
# Event IDs (single source of truth)
# ==============================
# Backup
BACKUP_START = "backup.start"
BACKUP_DIFF = "backup.diff"
BACKUP_SKIP = "backup.skip"
BACKUP_COPY = "backup.copy"
BACKUP_COMPRESS = "backup.compress"
BACKUP_ENCRYPT = "backup.encrypt"
BACKUP_CHECKSUM = "backup.checksum"
BACKUP_REGISTER = "backup.register"
BACKUP_COMPLETE = "backup.complete"
BACKUP_ABORT = "backup.abort"

# Restore
RESTORE_START = "restore.start"
RESTORE_VERIFY = "restore.verify"
RESTORE_SKIP = "restore.skip"
RESTORE_EXTRACT = "restore.extract"
RESTORE_METADATA = "restore.metadata"
RESTORE_COMPLETE = "restore.complete"
RESTORE_ABORT = "restore.abort"

# ==============================
# JSON Log Formatter
# ==============================
class JSONLogFormatter(logging.Formatter):
    """
    Enterprise-grade JSON log formatter.
    One log entry == one JSON object (single line).
    """
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "schema": LOG_SCHEMA,
            "version": LOG_SCHEMA_VERSION,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "component": getattr(record, "component", "unknown"),
            "event": getattr(record, "event", "unspecified"),
            "message": record.getMessage(),
        }

        context = getattr(record, "context", None)
        if isinstance(context, dict) and context:
            payload["context"] = context

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


# ==============================
# Root logger hard-silencing
# ==============================
_root_logger = logging.getLogger()
_root_logger.handlers.clear()
_root_logger.addHandler(logging.NullHandler())


# ==============================
# Custom Logger subclass to inject component
# ==============================
class ComponentLogger(logging.Logger):
    def __init__(self, name: str, component: str):
        super().__init__(name)
        self.component = component

    def makeRecord(
        self, *args, **kwargs
    ) -> logging.LogRecord:
        record = super().makeRecord(*args, **kwargs)
        record.component = self.component  # inject component into every record
        return record


# ==============================
# Logger factory
# ==============================
def get_logger(
    *,
    name: str,
    log_dir: Path,
    ts: str,
    component: str,
) -> logging.Logger:
    """
    Create a file-only, JSON-structured logger with automatic component injection.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{component}_{ts}.log"

    # Create logger instance manually
    logger = ComponentLogger(name, component)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Clear any existing handlers
    if logger.handlers:
        logger.handlers.clear()

    # Attach JSON file handler
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(JSONLogFormatter())
    logger.addHandler(handler)

    return logger

