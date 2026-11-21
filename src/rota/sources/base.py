"""Common source interface."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional

from ..http import Http


@dataclass
class Posting:
    """What a source yields before role matching/normalization."""

    source: str
    board: str
    external_id: str
    company: str
    title: str
    text: str
    location: str = ""
    url: str = ""
    remote: bool = False
    published_at: Optional[str] = None
    region: Optional[str] = None  # sources may force a region (e.g. Himalayas)
    role_hint: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def job_key(self) -> str:
        return f"{self.source}:{self.board}:{self.external_id}"


TitleFilter = Callable[[str], bool]


class Source:
    name: str = "base"
    refetchable: bool = False

    def __init__(self, http: Http, cfg: dict[str, Any]):
        self.http = http
        self.cfg = cfg or {}

    def fetch(self, roles: dict[str, dict[str, Any]], keep: TitleFilter) -> Iterator[Posting]:
        raise NotImplementedError

    def fetch_one(self, board: str, external_id: str) -> Posting | None:  # used by eval
        return None

    def check(self) -> list[tuple[str, int | None]]:
        """Return (board, n_jobs or None if not found) for configured boards."""
        return []


def ts_to_iso(v: Any) -> Optional[str]:
    """Accept unix seconds/millis or ISO strings."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        x = float(v)
        if x > 1e11:  # milliseconds
            x /= 1000
        return datetime.fromtimestamp(x, tz=timezone.utc).replace(microsecond=0).isoformat()
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None
