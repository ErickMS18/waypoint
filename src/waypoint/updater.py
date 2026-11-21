"""Background update ("Atualizar tudo") shared by the UI, the CLI and the desktop shortcut.

The update runs in a separate, window-less process (`waypoint update`) and reports progress in
data/logs/update_status.json, so the interface stays responsive and closing the browser tab
does not interrupt it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .settings import Config

STATUS_FILE = "update_status.json"
SETTINGS_FILE = "ui_settings.json"
DEFAULT_SETTINGS = {"auto_update_on_open": True, "auto_update_hours": 20, "theme": "dark", "lang": "pt"}


def _logs(cfg: Config) -> Path:
    p = cfg.paths.data / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def status_path(cfg: Config) -> Path:
    return _logs(cfg) / STATUS_FILE


def pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    if os.name == "nt":  # os.kill(pid, 0) would TERMINATE the process on Windows
        import ctypes
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_status(cfg: Config) -> dict[str, Any]:
    p = status_path(cfg)
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (json.JSONDecodeError, OSError):
        d = {}
    if d.get("state") == "running" and not pid_alive(d.get("pid")):
        d["state"] = "failed"
        d["error"] = d.get("error") or "O processo de atualização foi interrompido."
    return d


def write_status(cfg: Config, **kw: Any) -> None:
    p = status_path(cfg)
    cur: dict[str, Any] = {}
    if p.exists():
        try:
            cur = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cur = {}
    cur.update(kw, heartbeat=datetime.now().isoformat(timespec="seconds"))
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def is_running(cfg: Config) -> bool:
    return read_status(cfg).get("state") == "running"


def _no_window_flags() -> int:
    return 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


def python_exe() -> str:
    """Prefer pythonw.exe on Windows so no console window ever shows up."""
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "python.exe":
        w = exe.with_name("pythonw.exe")
        if w.exists():
            return str(w)
    return str(exe)


def start_background_update(cfg: Config) -> bool:
    """Spawn `waypoint update` in the background. Returns False if one is already running."""
    if is_running(cfg):
        return False
    log = open(_logs(cfg) / "update.log", "w", encoding="utf-8")
    env = {**os.environ, "WAYPOINT_HOME": str(cfg.paths.root), "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen([python_exe(), "-m", "waypoint.cli", "update"], cwd=str(cfg.paths.root), env=env,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=_no_window_flags())
    write_status(cfg, state="running", pid=proc.pid, msg="Iniciando…", frac=0.0,
                 started=datetime.now().strftime("%d/%m/%Y %H:%M"), error=None, result=None)
    return True


def run_update(cfg: Config) -> dict[str, Any]:
    """Body of `waypoint update` (runs in the background process)."""
    from .db import DB
    from .llm import LLMNotConfigured, make_client
    from .pipeline import update_all

    write_status(cfg, state="running", pid=os.getpid(), msg="Iniciando…", frac=0.0,
                 started=datetime.now().strftime("%d/%m/%Y %H:%M"), error=None, result=None)
    db = DB(cfg.paths.db)
    try:
        try:
            client = make_client(db)
        except LLMNotConfigured:
            client = None
        last = [0.0]

        def progress(msg: str, frac: float) -> None:
            print(msg, flush=True)
            now = time.monotonic()
            if now - last[0] > 0.7 or frac >= 1.0:
                write_status(cfg, msg=msg, frac=round(frac, 3))
                last[0] = now

        res = update_all(cfg, db, client=client, progress=progress)
        if client is None:
            res["aviso"] = "Sem chave de LLM no .env: usei só o extrator por dicionário."
        write_status(cfg, state="done", msg="Atualização concluída.", frac=1.0, result=res,
                     finished=datetime.now().strftime("%d/%m/%Y %H:%M"))
        return res
    except Exception as e:  # surface the error in the UI
        write_status(cfg, state="failed", error=f"{type(e).__name__}: {e}",
                     finished=datetime.now().strftime("%d/%m/%Y %H:%M"))
        raise
    finally:
        db.conn.close()


# --- small per-machine UI settings (data/ is git-ignored)
def load_ui_settings(cfg: Config) -> dict[str, Any]:
    p = cfg.paths.data / SETTINGS_FILE
    d = dict(DEFAULT_SETTINGS)
    if p.exists():
        try:
            d.update(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return d


def save_ui_settings(cfg: Config, **kw: Any) -> None:
    d = load_ui_settings(cfg)
    d.update(kw)
    cfg.paths.data.mkdir(parents=True, exist_ok=True)
    (cfg.paths.data / SETTINGS_FILE).write_text(json.dumps(d, indent=2), encoding="utf-8")


def hours_since_last_update(cfg: Config) -> Optional[float]:
    p = cfg.paths.data / "last_update.txt"
    if not p.exists():
        return None
    try:
        t = datetime.strptime(p.read_text(encoding="utf-8").strip(), "%d/%m/%Y %H:%M")
    except ValueError:
        return None
    return (datetime.now() - t).total_seconds() / 3600
