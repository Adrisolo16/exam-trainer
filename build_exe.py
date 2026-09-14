"""Compila la app a un .exe portable (un solo archivo)."""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "ExamTrainer"

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--clean",
    "--name", NAME,
    "--add-data", f"{HERE / 'data'}{';'}data",
    "--distpath", str(HERE / "dist"),
    "--workpath", str(HERE / "build"),
    "--specpath", str(HERE / "build"),
    str(HERE / "trainer.py"),
]

print(" ".join(cmd))
rc = subprocess.call(cmd, cwd=HERE)
if rc != 0:
    raise SystemExit(f"PyInstaller fallo con codigo {rc}")

exe = HERE / "dist" / f"{NAME}.exe"
print(f"\nListo: {exe}  ({exe.stat().st_size/1024/1024:.1f} MB)")

for junk in (HERE / "build",):
    shutil.rmtree(junk, ignore_errors=True)
