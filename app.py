import os
import sys

if sys.stdout is None or sys.stderr is None:   # Programm ohne Konsolenfenster (Windows-Installer): Meldungen in eine Logdatei
    from pathlib import Path

    _log_dir = Path(os.environ.get("ANONYMISIERUNGSTOOL_HOME") or Path.home() / ".anonymisierungstool")
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log = open(_log_dir / "programm.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

from anonymisierungstool.server import main

if __name__ == "__main__":
    main()
