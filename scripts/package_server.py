import argparse
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NAME = "mybattlezone-server"

SERVER_PATHS = [
    "battlezone",
    "config",
    "models",
    "sfx",
    "scripts/run_server.ps1",
    "scripts/run_server.sh",
    "Dockerfile",
    "requirements.txt",
    "test02.py",
    "README.md",
    "docs/lan_deployment.md",
]


def copy_path(source, target):
    if source.is_dir():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def build_server_bundle(name=DEFAULT_NAME):
    dist_dir = ROOT / "dist"
    staging_dir = dist_dir / name
    zip_path = dist_dir / f"{name}.zip"

    dist_dir.mkdir(exist_ok=True)
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    if zip_path.exists():
        zip_path.unlink()
    staging_dir.mkdir()

    for relative in SERVER_PATHS:
        source = ROOT / relative
        if not source.exists():
            raise FileNotFoundError(f"Missing server bundle path: {relative}")
        copy_path(source, staging_dir / relative)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in staging_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(dist_dir))

    return zip_path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Build the Battlezone server ZIP.")
    parser.add_argument("--name", default=DEFAULT_NAME, help="Bundle folder and ZIP base name.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    zip_path = build_server_bundle(args.name)
    print(zip_path)


if __name__ == "__main__":
    main()
