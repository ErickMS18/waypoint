"""Local SQLite storage (data/waypoint.db — git-ignored)."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import Job, JobExtraction, now_iso, text_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    board TEXT,
    external_id TEXT,
    company TEXT,
    title TEXT,
    location TEXT,
    region TEXT,
    remote INTEGER,
    url TEXT,
    published_at TEXT,
    collected_at TEXT,
    last_seen_at TEXT,
    role TEXT,
    lang TEXT,
    text TEXT,
    text_hash TEXT
);
CREATE INDEX IF NOT EXISTS ix_jobs_hash ON jobs(text_hash);
CREATE INDEX IF NOT EXISTS ix_jobs_role ON jobs(role);

CREATE TABLE IF NOT EXISTS extractions (
    job_key TEXT NOT NULL,
    extractor TEXT NOT NULL,       -- "llm" | "baseline"
    model TEXT,
    prompt_version TEXT,
    text_hash TEXT,
    data TEXT NOT NULL,            -- JobExtraction JSON
    created_at TEXT,
    PRIMARY KEY (job_key, extractor)
);

CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    created_at TEXT
);
"""


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---------- jobs ----------
    def upsert_job(self, job: Job) -> str:
        """Insert or refresh a job. Returns "new", "seen" or "duplicate"."""
        h = text_hash(job.text)
        cur = self.conn.execute("SELECT job_key FROM jobs WHERE job_key = ?", (job.job_key,))
        if cur.fetchone():
            self.conn.execute(
                "UPDATE jobs SET last_seen_at=?, text=?, text_hash=?, title=?, location=?, region=?, role=? WHERE job_key=?",
                (now_iso(), job.text, h, job.title, job.location, job.region, job.role, job.job_key),
            )
            return "seen"
        dup = self.conn.execute(
            "SELECT job_key FROM jobs WHERE text_hash = ? OR (lower(company)=lower(?) AND lower(title)=lower(?) AND lower(location)=lower(?))",
            (h, job.company, job.title, job.location),
        ).fetchone()
        if dup or self._near_duplicate(job.company, job.text):
            return "duplicate"
        self.conn.execute(
            """INSERT INTO jobs (job_key, source, board, external_id, company, title, location, region, remote,
                   url, published_at, collected_at, last_seen_at, role, lang, text, text_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job.job_key, job.source, job.board, job.external_id, job.company, job.title, job.location,
             job.region, int(job.remote), job.url, job.published_at, job.collected_at, now_iso(), job.role,
             job.lang, job.text, h),
        )
        return "new"

    def _near_duplicate(self, company: str, text: str, exclude_key: str = "") -> str | None:
        """Same company and nearly the same text (e.g. one opening posted in several cities)."""
        words = _word_set(text)
        rows = self.conn.execute("SELECT job_key, text FROM jobs WHERE lower(company)=lower(?) AND job_key != ?",
                                 (company, exclude_key)).fetchall()
        for r in rows:
            if jaccard(words, _word_set(r["text"])) >= NEAR_DUP_THRESHOLD:
                return r["job_key"]
        return None

    def delete_jobs(self, keys: list[str]) -> int:
        for k in keys:
            self.conn.execute("DELETE FROM jobs WHERE job_key=?", (k,))
            self.conn.execute("DELETE FROM extractions WHERE job_key=?", (k,))
        self.conn.commit()
        return len(keys)

    def remove_near_duplicates(self) -> int:
        """Keep the first-collected posting of each near-duplicate group."""
        rows = self.conn.execute("SELECT job_key, company, text FROM jobs ORDER BY collected_at, job_key").fetchall()
        kept: dict[str, list[set[str]]] = {}
        drop = []
        for r in rows:
            ws = _word_set(r["text"])
            group = kept.setdefault((r["company"] or "").lower(), [])
            if any(jaccard(ws, k) >= NEAR_DUP_THRESHOLD for k in group):
                drop.append(r["job_key"])
            else:
                group.append(ws)
        return self.delete_jobs(drop)

    def jobs(self, role: str | None = None) -> list[Job]:
        q = "SELECT * FROM jobs" + (" WHERE role = ?" if role else "") + " ORDER BY collected_at"
        rows = self.conn.execute(q, (role,) if role else ()).fetchall()
        return [_row_to_job(r) for r in rows]

    def job(self, job_key: str) -> Job | None:
        r = self.conn.execute("SELECT * FROM jobs WHERE job_key = ?", (job_key,)).fetchone()
        return _row_to_job(r) if r else None

    def count_jobs(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    # ---------- extractions ----------
    def save_extraction(self, job_key: str, extractor: str, ext: JobExtraction, *, model: str = "",
                        prompt_version: str = "", text_hash_: str = "") -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO extractions (job_key, extractor, model, prompt_version, text_hash, data, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (job_key, extractor, model, prompt_version, text_hash_, ext.model_dump_json(), now_iso()),
        )

    def extraction(self, job_key: str, extractor: str) -> tuple[JobExtraction, dict] | None:
        r = self.conn.execute(
            "SELECT * FROM extractions WHERE job_key=? AND extractor=?", (job_key, extractor)
        ).fetchone()
        if not r:
            return None
        meta = {k: r[k] for k in ("model", "prompt_version", "text_hash", "created_at")}
        return JobExtraction.model_validate_json(r["data"]), meta

    def extractions(self, extractor: str) -> dict[str, JobExtraction]:
        rows = self.conn.execute("SELECT job_key, data FROM extractions WHERE extractor=?", (extractor,)).fetchall()
        return {r["job_key"]: JobExtraction.model_validate_json(r["data"]) for r in rows}

    # ---------- LLM cache ----------
    def cache_get(self, key: str) -> str | None:
        r = self.conn.execute("SELECT response FROM llm_cache WHERE key=?", (key,)).fetchone()
        return r["response"] if r else None

    def cache_put(self, key: str, response: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO llm_cache (key, response, created_at) VALUES (?,?,?)",
                          (key, response, now_iso()))
        self.conn.commit()


def _row_to_job(r: sqlite3.Row) -> Job:
    d = dict(r)
    d.pop("last_seen_at", None)
    d.pop("text_hash", None)
    d["remote"] = bool(d.get("remote"))
    return Job(**{k: (v if v is not None else "") if k not in ("published_at",) else v for k, v in d.items()})


NEAR_DUP_THRESHOLD = 0.85


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9à-ÿ+#]+", (text or "").lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
