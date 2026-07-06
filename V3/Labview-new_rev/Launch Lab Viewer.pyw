"""No-console launcher for the HVAC Lab Viewer app."""

from __future__ import annotations

import os
import runpy
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"


def show_error(message: str) -> None:
    try:
        import tkinter.messagebox as messagebox

        messagebox.showerror("Lab Viewer launch failed", message)
    except Exception:
        pass


def main() -> None:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.argv = [str(APP)]

    try:
        runpy.run_path(str(APP), run_name="__main__")
    except Exception:
        error = traceback.format_exc()
        logs = ROOT / "logs"
        logs.mkdir(exist_ok=True)
        (logs / "launcher_error.log").write_text(error, encoding="utf-8")
        show_error(
            "The Lab Viewer could not start.\n\n"
            f"Details were written to:\n{logs / 'launcher_error.log'}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
