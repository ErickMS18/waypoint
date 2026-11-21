"""One-click launcher: starts the interface in the background (no terminal) and opens the browser.

Used by the desktop shortcut (scripts/waypoint_launcher.pyw) and by `waypoint ui`.
If the interface is already running it just opens the browser. If the last update is older
than `auto_update_hours` (and auto-update is on), it also starts an update in the background;
the home page shows its progress live.
"""
from __future__ import annotations

import os
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


def start_server(root: Path) -> subprocess.Popen:
    from .updater import _no_window_flags, python_exe
    logs = root / "data" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    app_file = Path(__file__).parent / "ui" / "app.py"
    env = {**os.environ, "WAYPOINT_HOME": str(root), "PYTHONIOENCODING": "utf-8"}
    cmd = [python_exe(), "-m", "streamlit", "run", str(app_file), "--server.headless", "true",
           "--server.port", str(PORT), "--server.address", "localhost", "--browser.gatherUsageStats", "false",
           "--theme.base", "light", "--theme.primaryColor", "#2a78d6", "--client.toolbarMode", "minimal"]
    return subprocess.Popen(cmd, cwd=str(root), env=env, stdout=open(logs / "ui.log", "w", encoding="utf-8"),
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=_no_window_flags())


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
    if not server_up():
        start_server(cfg.paths.root)
        for _ in range(120):  # up to ~60 s on a cold start
            if server_up():
                break
            time.sleep(0.5)
        else:
            _alert("Não consegui abrir a interface do Waypoint.\nVeja o arquivo data\\logs\\ui.log.")
            return 1
    if open_browser:
        webbrowser.open(URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
