"""
Convenience launcher for Web Data Forge Studio UI.
Usage: python run_app.py
"""

from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    app_path = Path(__file__).resolve().parent / "src" / "web_data_forge" / "ui" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    subprocess.run(cmd)
