from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AgentState:
    status: str = "stopped"
    backend_ready: bool = False
    checked_at: str = ""
    failure_count: int = 0
    last_error: str = ""
    last_recovery_at: str = ""
    history: list[str] = field(default_factory=list)

    def mark(self, status: str, note: str = "") -> None:
        self.status = status
        self.checked_at = datetime.now(timezone.utc).isoformat()
        if note:
            self.last_error = note
            self.history.append(f"{self.checked_at} {status} {note}")
        else:
            self.history.append(f"{self.checked_at} {status}")
