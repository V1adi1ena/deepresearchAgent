"""Use the project's overlay packages with its base Python on Windows."""
from pathlib import Path
import os
import sys


def use_project_packages(root: Path) -> None:
    packages = root / ".venv/Lib/site-packages"
    config = root / ".venv/pyvenv.cfg"
    if os.name != "nt" or sys.prefix != sys.base_prefix or not packages.is_dir():
        return
    values = dict(line.split(" = ", 1) for line in config.read_text().splitlines() if " = " in line)
    version = values.get("version", "").split(".")[:2]
    if version != [str(sys.version_info.major), str(sys.version_info.minor)]:
        raise RuntimeError("Project .venv and base Python must have the same Python major/minor version.")
    sys.path.insert(0, str(packages))
