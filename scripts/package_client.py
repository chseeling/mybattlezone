import argparse
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NAME = "mybattlezone-client"

CLIENT_PATHS = [
    "battlezone",
    "config",
    "models",
    "sfx",
    "client_launcher.py",
    "play_client.ps1",
    "play_client.sh",
    "start_client.ps1",
    "start_client.sh",
    "requirements.txt",
    "battlezone_game.py",
    "README.md",
    "docs/lan_deployment.md",
]


def copy_path(source, target):
    if source.is_dir():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def build_client_bundle(name=DEFAULT_NAME):
    dist_dir = ROOT / "dist"
    staging_dir = dist_dir / name
    zip_path = dist_dir / f"{name}.zip"

    dist_dir.mkdir(exist_ok=True)
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    if zip_path.exists():
        zip_path.unlink()
    staging_dir.mkdir()

    for relative in CLIENT_PATHS:
        source = ROOT / relative
        if not source.exists():
            raise FileNotFoundError(f"Missing client bundle path: {relative}")
        copy_path(source, staging_dir / relative)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in staging_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(dist_dir))

    return zip_path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Build the Battlezone client-only ZIP.")
    parser.add_argument("--name", default=DEFAULT_NAME, help="Bundle folder and ZIP base name.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    zip_path = build_client_bundle(args.name)
    print(zip_path)


if __name__ == "__main__":
    main()
