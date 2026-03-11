#!/usr/bin/env python3

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def ensure_pip_available() -> None:
    if importlib.util.find_spec("pip") is not None:
        return

    subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])


def pip_install_command(requirements_file: Path, package_dir: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-compile",
        "--target",
        str(package_dir),
        "-r",
        str(requirements_file),
    ]

    if sys.platform == "win32":
        command.extend(
            [
                "--platform",
                "manylinux2014_x86_64",
                "--implementation",
                "cp",
                "--python-version",
                "3.12",
                "--only-binary=:all:",
            ]
        )

    return command


def remove_tree(path: Path, raise_on_error: bool = True) -> None:
    if not path.exists():
        return

    last_error = None
    for _ in range(5):
        try:
            shutil.rmtree(path)
            return
        except PermissionError as exc:
            last_error = exc
            import time
            time.sleep(1)

    if raise_on_error and last_error is not None:
        raise last_error


def replace_file(source: Path, destination: Path) -> None:
    last_error = None
    for _ in range(5):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            last_error = exc
            import time
            time.sleep(1)

    if last_error is not None:
        raise last_error


def build_package() -> Path:
    module_dir = Path(__file__).resolve().parent
    project_root = module_dir.parents[2]
    build_dir = Path(tempfile.mkdtemp(prefix="frontier-build-", dir=module_dir))
    package_dir = build_dir / "package"
    zip_path = module_dir / "lambda" / "frontier_agent.zip"
    temp_zip_path = build_dir / "frontier_agent.zip"
    requirements_file = project_root / "src" / "agents" / "FrontierAgent" / "requirements.lambda.txt"

    package_dir.mkdir(parents=True, exist_ok=True)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_pip_available()

    subprocess.check_call(pip_install_command(requirements_file, package_dir))

    files_to_copy = {
        project_root / "src" / "__init__.py": package_dir / "src" / "__init__.py",
        project_root / "src" / "agents" / "__init__.py": package_dir / "src" / "agents" / "__init__.py",
        project_root / "src" / "agents" / "agent.py": package_dir / "src" / "agents" / "agent.py",
        project_root / "src" / "agents" / "FrontierAgent" / "frontier_agent.py": package_dir / "src" / "agents" / "FrontierAgent" / "frontier_agent.py",
        project_root / "src" / "agents" / "FrontierAgent" / "lambda_handler.py": package_dir / "src" / "agents" / "FrontierAgent" / "lambda_handler.py",
    }

    for source, destination in files_to_copy.items():
        copy_file(source, destination)

    with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in package_dir.rglob("*"):
            if file_path.is_file() and "__pycache__" not in file_path.parts and not file_path.name.endswith(".pyc"):
                zip_file.write(file_path, file_path.relative_to(package_dir))

    replace_file(temp_zip_path, zip_path)
    remove_tree(build_dir, raise_on_error=False)
    return zip_path


if __name__ == "__main__":
    package_path = build_package()
    print(package_path)
