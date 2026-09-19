#!/usr/bin/env python3
"""Build the midlevel-practitioners snapshot (CSV + Parquet + DuckDB) from a
raw NPPES npidata_pfile CSV, then archive it into data/processed/YYYY-MM/
and prune snapshots older than RETENTION_MONTHS.

Usage:
    python3 build_snapshot.py <path-to-npidata_pfile.csv> [YYYY-MM]

If YYYY-MM is omitted, the current year-month is used.
"""
import csv
import json
import shutil
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_REF = ROOT / "config" / "taxonomy_codes.csv"
PROCESSED_DIR = ROOT / "data" / "processed"
RETENTION_MONTHS = 12
TABLE_NAME = "midlevel_practitioners"


def load_target_codes():
    with open(TAXONOMY_REF, newline="", encoding="utf-8") as f:
        return [row["taxonomy_code"] for row in csv.DictReader(f)]


def get_csv_columns(csv_path: Path) -> list[str]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f))


def cols_matching(columns, prefix):
    """Return columns starting with `prefix` followed by an underscore + number, sorted 1..15."""
    matches = [c for c in columns if c.startswith(prefix + "_")]
    matches.sort(key=lambda c: int(c.rsplit("_", 1)[-1]))
    return matches


def q(col: str) -> str:
    return '"' + col.replace('"', '""') + '"'


def build_matched_case(taxonomy_cols, license_num_cols, license_state_cols, switch_cols, target_codes_sql):
    """Build three parallel CASE expressions (code / license number / license state),
    preferring a slot marked as the primary taxonomy, falling back to the first
    matching slot in declared order."""
    n = len(taxonomy_cols)

    def whens(field_cols, require_primary):
        lines = []
        for i in range(n):
            cond = f"{q(taxonomy_cols[i])} IN ({target_codes_sql})"
            if require_primary:
                cond += f" AND UPPER(TRIM({q(switch_cols[i])})) = 'Y'"
            lines.append(f"WHEN {cond} THEN {q(field_cols[i])}")
        return "\n    ".join(lines)

    def case_expr(field_cols):
        return (
            "CASE\n    " + whens(field_cols, True) + "\n    " + whens(field_cols, False) + "\n  END"
        )

    return {
        "matched_taxonomy_code": case_expr(taxonomy_cols),
        "matched_license_number": case_expr(license_num_cols),
        "matched_license_state": case_expr(license_state_cols),
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: build_snapshot.py <npidata_pfile.csv> [YYYY-MM]")
    src_csv = Path(sys.argv[1])
    snapshot_id = sys.argv[2] if len(sys.argv) > 2 else time.strftime("%Y-%m")

    target_codes = load_target_codes()
    target_codes_sql = ",".join(f"'{c}'" for c in target_codes)

    columns = get_csv_columns(src_csv)
    taxonomy_cols = cols_matching(columns, "Healthcare Provider Taxonomy Code")
    switch_cols = cols_matching(columns, "Healthcare Provider Primary Taxonomy Switch")
    license_num_cols = [c for c in cols_matching(columns, "Provider License Number") if "State" not in c]
    license_state_cols = cols_matching(columns, "Provider License Number State Code")
    assert len(taxonomy_cols) == len(switch_cols) == len(license_num_cols) == len(license_state_cols) >= 1, (
        "Unexpected NPPES column layout â€” taxonomy/switch/license slot counts do not match. "
        "CMS may have changed the file format; inspect the header manually."
    )
    print(f"Found {len(taxonomy_cols)} taxonomy slots in source file.")

    matched = build_matched_case(taxonomy_cols, license_num_cols, license_state_cols, switch_cols, target_codes_sql)
    taxonomy_filter = " OR ".join(f"{q(c)} IN ({target_codes_sql})" for c in taxonomy_cols)

    # Output columns: NPI identity, name, credential, gender, matched practitioner
    # taxonomy/license, primary declared taxonomy, mailing + practice addresses,
    # phone/fax, key dates, and sole-proprietor flag.
    select_list = f"""
        {q('NPI')} AS npi,
        {q('Provider Last Name (Legal Name)')} AS last_name,
        {q('Provider First Name')} AS first_name,
        {q('Provider Middle Name')} AS middle_name,
        {q('Provider Name Prefix Text')} AS name_prefix,
        {q('Provider Name Suffix Text')} AS name_suffix,
        {q('Provider Credential Text')} AS credential_text,
        {q('Provider Sex Code')} AS sex_code,
        tax_ref.practitioner_type AS practitioner_type,
        tax_ref.classification AS practitioner_classification,
        tax_ref.specialization AS practitioner_specialization,
        matched.matched_taxonomy_code AS matched_taxonomy_code,
        matched.matched_license_number AS license_number,
        matched.matched_license_state AS license_state,
        {q('Healthcare Provider Taxonomy Code_1')} AS primary_taxonomy_code,
        {q('Provider First Line Business Practice Location Address')} AS practice_address_line1,
        {q('Provider Second Line Business Practice Location Address')} AS practice_address_line2,
        {q('Provider Business Practice Location Address City Name')} AS practice_city,
        {q('Provider Business Practice Location Address State Name')} AS practice_state,
        {q('Provider Business Practice Location Address Postal Code')} AS practice_zip,
        {q('Provider Business Practice Location Address Telephone Number')} AS practice_phone,
        {q('Provider Business Practice Location Address Fax Number')} AS practice_fax,
        {q('Provider First Line Business Mailing Address')} AS mailing_address_line1,
        {q('Provider Second Line Business Mailing Address')} AS mailing_address_line2,
        {q('Provider Business Mailing Address City Name')} AS mailing_city,
        {q('Provider Business Mailing Address State Name')} AS mailing_state,
        {q('Provider Business Mailing Address Postal Code')} AS mailing_zip,
        {q('Provider Business Mailing Address Telephone Number')} AS mailing_phone,
        {q('Provider Business Mailing Address Fax Number')} AS mailing_fax,
        {q('Provider Enumeration Date')} AS enumeration_date,
        {q('Last Update Date')} AS last_update_date,
        {q('Certification Date')} AS certification_date,
        {q('Is Sole Proprietor')} AS is_sole_proprietor
    """

    con = duckdb.connect()
    con.execute(f"PRAGMA threads={max(1, __import__('os').cpu_count() or 4)}")

    read_csv_expr = f"read_csv_auto('{src_csv.as_posix()}', all_varchar=True, header=True)"

    query = f"""
        WITH src AS (
            SELECT *,
                {matched['matched_taxonomy_code']} AS __matched_taxonomy_code,
                {matched['matched_license_number']} AS __matched_license_number,
                {matched['matched_license_state']} AS __matched_license_state
            FROM {read_csv_expr}
            WHERE {q('Entity Type Code')} = '1'
              AND ({q('NPI Deactivation Date')} IS NULL OR TRIM({q('NPI Deactivation Date')}) = '')
              AND ({taxonomy_filter})
        )
        SELECT
            {select_list.replace('matched.matched_taxonomy_code', 'src.__matched_taxonomy_code')
                        .replace('matched.matched_license_number', 'src.__matched_license_number')
                        .replace('matched.matched_license_state', 'src.__matched_license_state')}
        FROM src
        LEFT JOIN read_csv_auto('{TAXONOMY_REF.as_posix()}', header=True) AS tax_ref
          ON src.__matched_taxonomy_code = tax_ref.taxonomy_code
    """

    print("Running DuckDB extraction/transform query (this scans the full source file once)...")
    t0 = time.time()
    con.execute(f"CREATE TABLE {TABLE_NAME} AS {query}")
    row_count = con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    print(f"Matched {row_count:,} active individual midlevel-practitioner NPIs in {time.time()-t0:.0f}s")

    out_dir = PROCESSED_DIR / snapshot_id
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{TABLE_NAME}.csv"
    parquet_path = out_dir / f"{TABLE_NAME}.parquet"
    duckdb_path = out_dir / f"{TABLE_NAME}.duckdb"

    con.execute(f"COPY {TABLE_NAME} TO '{csv_path.as_posix()}' (HEADER, DELIMITER ',')")
    con.execute(f"COPY {TABLE_NAME} TO '{parquet_path.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()

    if duckdb_path.exists():
        duckdb_path.unlink()
    dcon = duckdb.connect(duckdb_path.as_posix())
    dcon.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM read_parquet('{parquet_path.as_posix()}')")
    dcon.close()

    manifest = {
        "snapshot_id": snapshot_id,
        "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_file": src_csv.name,
        "row_count": row_count,
        "taxonomy_codes_included": len(target_codes),
        "files": {
            "csv": csv_path.name,
            "parquet": parquet_path.name,
            "duckdb": duckdb_path.name,
        },
    }
    with open(out_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote snapshot to {out_dir}")

    update_current_pointer(snapshot_id)
    sync_latest_dir(out_dir)
    prune_old_snapshots()


def update_current_pointer(snapshot_id: str):
    current_link = ROOT / "data" / "current"
    target = Path("processed") / snapshot_id
    if current_link.is_symlink() or current_link.exists():
        current_link.unlink()
    current_link.symlink_to(target)
    print(f"Updated data/current -> {target}")


GITHUB_FILE_SIZE_WARN_BYTES = 90 * 1024 * 1024  # GitHub hard-blocks single files > 100MB


def sync_latest_dir(snapshot_dir: Path):
    """Copy the just-built snapshot's files into the git-tracked latest/ dir,
    which always holds only the current month (full archive stays local-only
    under data/processed/). The CSV is gzipped here since the raw CSV can
    exceed GitHub's 100MB per-file push limit; parquet/duckdb are copied as-is."""
    import gzip

    latest_dir = ROOT / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    latest_dir.mkdir(parents=True)

    for name in ("manifest.json", f"{TABLE_NAME}.parquet", f"{TABLE_NAME}.duckdb"):
        src = snapshot_dir / name
        dest = latest_dir / name
        shutil.copy2(src, dest)
        if dest.stat().st_size > GITHUB_FILE_SIZE_WARN_BYTES:
            print(f"WARNING: {dest.name} is {dest.stat().st_size/1e6:.0f}MB, "
                  f"approaching GitHub's 100MB per-file push limit.")

    csv_src = snapshot_dir / f"{TABLE_NAME}.csv"
    csv_gz_dest = latest_dir / f"{TABLE_NAME}.csv.gz"
    with open(csv_src, "rb") as f_in, gzip.open(csv_gz_dest, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    if csv_gz_dest.stat().st_size > GITHUB_FILE_SIZE_WARN_BYTES:
        print(f"WARNING: {csv_gz_dest.name} is {csv_gz_dest.stat().st_size/1e6:.0f}MB, "
              f"approaching GitHub's 100MB per-file push limit.")

    print(f"Synced current snapshot to {latest_dir} (git-tracked; CSV gzipped)")


def prune_old_snapshots():
    snapshots = sorted(p.name for p in PROCESSED_DIR.iterdir() if p.is_dir())
    if len(snapshots) <= RETENTION_MONTHS:
        return
    to_remove = snapshots[: len(snapshots) - RETENTION_MONTHS]
    for name in to_remove:
        path = PROCESSED_DIR / name
        print(f"Pruning snapshot older than {RETENTION_MONTHS} months: {path}")
        shutil.rmtree(path)


if __name__ == "__main__":
    main()
