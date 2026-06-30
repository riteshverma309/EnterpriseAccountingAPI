"""Simple audit logging helpers for write operations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


AUDIT_LOG_PATH = Path("audit.log")


def write_audit_event(action: str, subject: str, details: Dict[str, Any], user: str = "system") -> None:
    """Append a JSON audit record to a local log file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "subject": subject,
        "user": user,
        "details": details,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
