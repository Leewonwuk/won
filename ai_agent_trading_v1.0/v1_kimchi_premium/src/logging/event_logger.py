from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

from src.models import utc_now_iso


@dataclass(slots=True)
class EventLogger:
    path: str
    _path: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        out = Path(self.path)
        out.parent.mkdir(parents=True, exist_ok=True)
        self._path = out

    def log(self, event_type: str, payload: dict) -> None:
        row = {"ts": utc_now_iso(), "event_type": event_type, **payload}
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

