"""
Convenience launcher for Web Data Forge Studio UI.
Usage: python run_app.py
"""

import os
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    root_dir = Path(__file__).resolve().parent
    src_dir = root_dir / "src"
    app_path = src_dir / "web_data_forge" / "ui" / "app.py"

    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{src_dir}{os.pathsep}{current_pythonpath}"
        if current_pythonpath
        else str(src_dir)
    )

    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    subprocess.run(cmd, env=env)

