# Atalho do Waypoint: abre a interface sem terminal (roda com pythonw.exe da .venv).
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("WAYPOINT_HOME", str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from waypoint.launcher import main  # noqa: E402

raise SystemExit(main())
