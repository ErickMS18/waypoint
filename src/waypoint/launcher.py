"""One-click launcher: starts the local app in the background (no terminal) and opens it in its own window.

Used by the desktop shortcut (scripts/waypoint_launcher.pyw) and by `waypoint ui`.
The window is Edge (or Chrome) in "app" mode: no tabs or address bar, its own taskbar entry. Without
either, it falls back to the default browser. If the app is already running it just opens the window. If the last update is older
than `auto_update_hours` (and auto-update is on), it also starts an update in the background;
the home page shows its progress live.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

HOST, PORT = "127.0.0.1", 8501
URL = f"http://localhost:{PORT}"


def server_up(timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout):
            return True
    except OSError:
        return False


def code_stamp() -> str:
    """Changes whenever the package code changes (used to restart an outdated server)."""
    pkg = Path(__file__).parent
    return str(max(int(p.stat().st_mtime) for p in pkg.rglob("*.py")))


def _info_path(root: Path) -> Path:
    return root / "data" / "logs" / "ui_server.json"


def register_server(root: Path) -> None:
    """Called by the running app: remember which process serves the UI and with which code version."""
    p = _info_path(root)
    try:
        cur = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cur = {}
    if cur.get("pid") != os.getpid():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"pid": os.getpid(), "stamp": code_stamp()}), encoding="utf-8")


def _pid_on_port() -> int | None:
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10,
                             creationflags=0x08000000).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(f":{PORT}") and parts[3].upper() in ("LISTENING", "ESCUTANDO"):
            try:
                return int(parts[4])
            except ValueError:
                return None
    return None


def stale_server_pid(root: Path) -> int | None:
    """PID of a running UI server whose code is older than the code on disk (None if it is current)."""
    try:
        info = json.loads(_info_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    if info.get("stamp") == code_stamp():
        return None
    return info.get("pid") or _pid_on_port()


def stop_server(pid: int) -> None:
    try:
        os.kill(int(pid), signal.SIGTERM)
    except (OSError, ValueError):
        return
    for _ in range(40):
        if not server_up():
            return
        time.sleep(0.25)


def start_server(root: Path) -> subprocess.Popen:
    from .updater import _no_window_flags, python_exe
    logs = root / "data" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "WAYPOINT_HOME": str(root), "PYTHONIOENCODING": "utf-8"}
    cmd = [python_exe(), "-m", "waypoint.web.server"]
    return subprocess.Popen(cmd, cwd=str(root), env=env, stdout=open(logs / "ui.log", "w", encoding="utf-8"),
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=_no_window_flags())


def app_browser() -> str | None:
    """Edge or Chrome executable, for an app-style window (Windows paths first, then PATH)."""
    import shutil
    cands = []
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
        if base:
            cands += [Path(base) / "Microsoft/Edge/Application/msedge.exe", Path(base) / "Google/Chrome/Application/chrome.exe"]
    for c in cands:
        if c.exists():
            return str(c)
    for name in ("msedge", "microsoft-edge", "google-chrome", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def open_window(root: Path) -> None:
    exe = app_browser()
    if not exe:
        webbrowser.open(URL)
        return
    profile = root / "data" / "app-window"  # a separate profile: its own window and taskbar icon
    profile.mkdir(parents=True, exist_ok=True)
    from .updater import _no_window_flags
    subprocess.Popen([exe, f"--app={URL}", f"--user-data-dir={profile}", "--window-size=1440,920",
                      "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=_no_window_flags(), close_fds=True)


def _alert(msg: str) -> None:
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "Waypoint", 0x10)  # type: ignore[attr-defined]
    else:
        print(msg, file=sys.stderr)


def main(open_browser: bool = True, auto_update: bool = True) -> int:
    from .settings import load_config
    cfg = load_config()
    cfg.paths.ensure()
    if auto_update:
        from .updater import hours_since_last_update, is_running, load_ui_settings, start_background_update
        s = load_ui_settings(cfg)
        age = hours_since_last_update(cfg)
        if s.get("auto_update_on_open") and not is_running(cfg) and age is not None and age >= float(s.get("auto_update_hours", 20)):
            start_background_update(cfg)
    if server_up():
        pid = stale_server_pid(cfg.paths.root)
        _log(cfg.paths.root, f"server up; outdated pid={pid}")
        if pid:  # the code was updated since the server started: restart it so the new version shows up
            stop_server(pid)
            _log(cfg.paths.root, f"stopped {pid}; still up={server_up()}")
    if not server_up():
        _log(cfg.paths.root, "starting server")
        start_server(cfg.paths.root)
        for _ in range(120):  # up to ~60 s on a cold start
            if server_up():
                break
            time.sleep(0.5)
        else:
            _alert("Não consegui abrir a interface do Waypoint.\nVeja o arquivo data\\logs\\ui.log.")
            return 1
    if open_browser:
        open_window(cfg.paths.root)
    return 0


def _log(root: Path, msg: str) -> None:
    try:
        p = root / "data" / "logs" / "launcher.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def safe_main() -> int:
    """Entry point for the desktop shortcut: never fails silently (writes data/logs/launcher.log)."""
    import traceback
    root = Path(os.environ.get("WAYPOINT_HOME") or Path.cwd())
    try:
        return main()
    except Exception:
        _log(root, traceback.format_exc())
        _alert("O Waypoint não conseguiu abrir. Veja data\\logs\\launcher.log.")
        return 1


if __name__ == "__main__":
    raise SystemExit(safe_main())
