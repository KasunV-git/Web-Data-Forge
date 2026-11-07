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

    # Automatically resolve the project's virtual environment python if present
    venv_py_win = root_dir / ".venv" / "Scripts" / "python.exe"
    venv_py_posix = root_dir / ".venv" / "bin" / "python"

    if venv_py_win.exists():
        python_executable = str(venv_py_win)
    elif venv_py_posix.exists():
        python_executable = str(venv_py_posix)
    else:
        python_executable = sys.executable

    env = os.environ.copy()
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{src_dir}{os.pathsep}{current_pythonpath}"
        if current_pythonpath
        else str(src_dir)
    )

    cmd = [
        python_executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--browser.gatherUsageStats=false",
    ]
    subprocess.run(cmd, env=env)

