from __future__ import annotations

from pathlib import Path

from app.core.audit import AUDIT_LOG_PATH, write_audit_event


def test_write_audit_event_appends_log_entry(tmp_path):
    import app.core.audit as audit_module

    audit_module.AUDIT_LOG_PATH = tmp_path / "audit.log"
    write_audit_event("create", "tenant", {"name": "Acme"}, user="alice")
    lines = (audit_module.AUDIT_LOG_PATH).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert '"action": "create"' in lines[0]
