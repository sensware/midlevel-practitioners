#!/usr/bin/env python3
"""Monthly orchestration: download the current NPPES full replacement file,
extract the main npidata_pfile, build the midlevel-practitioners snapshot,
and clean up the raw download (which is not versioned â€” only the built
snapshots under data/processed/ are kept).

Intended to be run by a monthly scheduled job (see README.md).
"""
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
LOGS_DIR = ROOT / "logs"


def run(cmd, **kwargs):
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def main():
    snapshot_id = time.strftime("%Y-%m")
    LOGS_DIR.mkdir(exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    zip_path = RAW_DIR / "npppes_download.zip"
    print(f"=== Monthly NPPES refresh: {snapshot_id} ===")

    run([sys.executable, str(ROOT / "scripts" / "download_nppes.py"), str(zip_path)])

    with zipfile.ZipFile(zip_path) as zf:
        main_csv_name = next(
            n for n in zf.namelist()
            if n.startswith("npidata_pfile_") and n.endswith(".csv") and "fileheader" not in n
        )
        print(f"Extracting {main_csv_name} ...")
        zf.extract(main_csv_name, RAW_DIR)
    main_csv_path = RAW_DIR / main_csv_name

    run([sys.executable, str(ROOT / "scripts" / "build_snapshot.py"), str(main_csv_path), snapshot_id])

    print("Cleaning up raw download (not versioned)...")
    zip_path.unlink(missing_ok=True)
    main_csv_path.unlink(missing_ok=True)

    publish_latest_to_github(snapshot_id)

    print(f"=== Done. Snapshot available at data/processed/{snapshot_id}/ and data/current ===")


def publish_latest_to_github(snapshot_id: str):
    """Commit+push latest/ (manifest, both summary CSVs, and the 1000-row
    sample csv+parquet -- never the full data) to `main` as a normal commit.
    No full dataset is ever pushed to GitHub, so there's no repo-size concern
    here and no need to rewrite history -- just a small incremental commit
    each month, same as any other code change."""
    import json

    manifest_path = ROOT / "latest" / "manifest.json"
    row_count = None
    if manifest_path.exists():
        row_count = json.loads(manifest_path.read_text()).get("row_count")

    remotes = subprocess.run(
        ["git", "remote"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    if "origin" not in remotes:
        print("No 'origin' git remote configured -- skipping GitHub publish.")
        return

    run(["git", "add", "latest/"], cwd=ROOT)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if diff.returncode == 0:
        print("No changes to latest/ example outputs -- nothing to publish.")
        return

    msg = f"Update example outputs: {snapshot_id}"
    if row_count is not None:
        msg += f" ({row_count:,} practitioners in full dataset; example is a 1000-row sample)"
    run(["git", "commit", "-q", "-m", msg], cwd=ROOT)
    run(["git", "push", "origin", "main"], cwd=ROOT)
    print(f"Pushed updated example outputs ({snapshot_id}) to GitHub main.")


if __name__ == "__main__":
    main()
