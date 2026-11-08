"""Build a native executable archive and SHA-256 file on the current OS."""

import hashlib
import importlib.metadata
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from packaging.requirements import Requirement


def copy_dependency_licenses(destination):
    """Retain runtime licenses, including modules included by frozen hooks."""
    pending = ["Flask", "requests", "waitress", "setuptools", "packaging"]
    seen, manifest = set(), []
    while pending:
        name = pending.pop()
        distribution = importlib.metadata.distribution(name)
        identity = distribution.metadata["Name"].lower()
        if identity in seen:
            continue
        seen.add(identity)
        manifest.append(f"{distribution.metadata['Name']}=={distribution.version}")
        for dependency in distribution.requires or []:
            requirement = Requirement(dependency)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
        for file in distribution.files or []:
            if file.name.lower().startswith(("license", "copying", "notice")):
                target = destination / identity / str(file).replace("\\", "__").replace("/", "__")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(distribution.locate_file(file), target)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "DEPENDENCIES.txt").write_text("\n".join(sorted(manifest)) + "\n", encoding="utf-8")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, destination / "Python-LICENSE.txt")

def main():
    root = Path(__file__).resolve().parent.parent
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "meteo.spec"], cwd=root, check=True)
    package = root / "dist" / "Meteo-Command"
    for filename in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "RELEASE_NOTES.md", "CHANGELOG.md", "Start-Meteo.cmd", "start.sh"):
        shutil.copy2(root / filename, package / filename)
    shutil.copytree(root / "docs", package / "docs", dirs_exist_ok=True)
    copy_dependency_licenses(package / "licenses")
    name = f"Meteo-Command-v{version}-{platform.system().lower()}-{platform.machine().lower()}"
    archive = Path(shutil.make_archive(str(root / "dist" / name), "zip", root_dir=root / "dist", base_dir="Meteo-Command"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(archive)


if __name__ == "__main__":
    main()
