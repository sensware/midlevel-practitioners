# Midlevel Practitioners Dataset

A monthly-refreshed list of active, individually-enumerated U.S. midlevel
practitioners (non-physician clinicians who can see patients and prescribe
medication), built from the CMS NPPES NPI file. Output as CSV, Parquet, and
DuckDB on every run, with the previous 12 monthly snapshots retained. Every
build verifies NPI uniqueness before writing output, and also produces
`summary_by_practitioner_type.csv` / `summary_by_state.csv` breakdowns.

**The full dataset is never uploaded anywhere — it lives only on this
machine.** GitHub gets a random 1,000-row sample (CSV + Parquet) plus the two
summary CSVs, purely as a schema/quality example.

## Scope

- **Practitioner types included** (57 NUCC taxonomy codes total, see
  `config/taxonomy_codes.csv`):
  - **NP** — Nurse Practitioner (18 codes, all specialties)
  - **PA** — Physician Assistant (3 codes)
  - **CNS** — Clinical Nurse Specialist (34 codes, all specialties)
  - **CRNA** — Certified Registered Nurse Anesthetist (1 code)
  - **CNM** — Advanced Practice (Certified Nurse) Midwife (1 code) — lay/direct-entry
    midwife codes (175M00000X, 176B00000X) are deliberately excluded since those
    are not APRNs and generally lack prescribing authority.
- **Entity type**: Individuals only (NPPES Entity Type Code 1). Organizational
  NPIs (Type 2) are excluded.
- **Geography**: All U.S. states/territories.
- **Active only**: Records with a populated `NPI Deactivation Date` are excluded.
- **Licensed only**: a record is only included if at least one of its matching
  taxonomy slots has BOTH a license number and a license state on file.
  NPPES has no separate "license active/expired" flag, so a populated license
  is the closest signal it provides that the provider is actually licensed
  (as opposed to just holding a taxonomy code with no attached credential).
  This currently excludes roughly 5% of otherwise-matching active NPIs, most
  of them PAs — see `unlicensed_matching_npis_excluded` in `manifest.json`.
- A provider is included if **any** of their up to 15 taxonomy slots matches
  the target list, not just their primary taxonomy — the primary slot is
  preferred when picking which matched code/license to report.

## Output columns

| Column | Notes |
|---|---|
| `npi` | 10-digit National Provider Identifier |
| `last_name`, `first_name`, `middle_name`, `name_prefix`, `name_suffix` | Legal name |
| `credential_text` | Self-reported credential string (e.g. `NP`, `PA-C`, `CRNA`) |
| `sex_code` | `M`/`F` |
| `practitioner_type` | `NP` / `PA` / `CNS` / `CRNA` / `CNM` |
| `practitioner_classification`, `practitioner_specialization` | From NUCC taxonomy |
| `matched_taxonomy_code`, `license_number`, `license_state` | From whichever taxonomy slot matched |
| `primary_taxonomy_code` | Provider's NPPES-declared primary taxonomy (slot 1) |
| `practice_address_line1/2`, `practice_city/state/zip`, `practice_phone`, `practice_fax` | Practice location — best for territory/geo marketing |
| `mailing_address_line1/2`, `mailing_city/state/zip`, `mailing_phone`, `mailing_fax` | Business mailing address |
| `created_date` | NPPES `Provider Enumeration Date` — when the NPI was first issued |
| `last_updated_date` | NPPES `Last Update Date` — most recent change to the NPPES record |
| `certification_date` | NPPES `Certification Date` |
| `is_sole_proprietor` | `Y`/`N` |

NPPES does not include email addresses; there is none in this dataset.

## Data quality checks

- **NPI uniqueness**: `build_snapshot.py` aborts (no output files written) if
  it finds any duplicate `npi` value in the filtered table. `manifest.json`
  records `duplicate_npis_found` (always `0` in a successful build).
- **Summary files**: each snapshot includes `summary_by_practitioner_type.csv`
  (provider count per NP/PA/CNS/CRNA/CNM) and `summary_by_state.csv` (provider
  count per `practice_state`), both mirrored into `latest/` and pushed to GitHub.
- **Sample files**: each snapshot also includes a `sample_midlevel_practitioners.csv`
  / `.parquet` — a random 1,000-row reservoir sample of the full table, same
  schema as the full dataset, safe to publish since it's a small subset.

## Compliance note (read before commercial use)

Taxonomy code **descriptions** (classification/specialization text) come from
the NUCC Health Care Provider Taxonomy Code Set. NUCC's terms require a
license for **commercial use** of the code set — [see their permission
request form](https://www.nucc.org). The underlying NPI/address/name data
from NPPES itself is public domain. Since this dataset is intended for
marketing, obtain a NUCC license before commercial use of the taxonomy
description text, or replace `practitioner_classification` /
`practitioner_specialization` with your own labels if you don't have one.

## Directory layout

```
config/taxonomy_codes.csv        curated list of the 57 target taxonomy codes
scripts/download_nppes.py        finds & downloads the current NPPES monthly zip
scripts/build_snapshot.py        filters/transforms -> full csv+parquet+duckdb, summaries, 1000-row sample; archives, prunes, syncs latest/
scripts/run_monthly.py           orchestrates the above; deletes raw download; commits+pushes latest/ to GitHub main
data/processed/YYYY-MM/          one dated snapshot per month: FULL csv/parquet/duckdb, 2 summary csvs, sample csv+parquet, manifest.json — LOCAL ONLY, NEVER PUSHED
data/current                     symlink to the latest data/processed/YYYY-MM — LOCAL ONLY
data/raw/                        scratch space for the ~1.1GB zip / ~11.7GB extracted CSV; deleted after each run
latest/                          current month's SMALL example outputs only (manifest, 2 summaries, sample csv+parquet) — GIT-TRACKED
```

`data/`, `data/raw/`, and `logs/` are gitignored — the full dataset and
12-month local archive live **only on this machine** and are never uploaded
anywhere. `latest/` is the one thing that's git-tracked and pushed to GitHub
(https://github.com/sensware/midlevel-practitioners), and it holds only:
`manifest.json`, `summary_by_practitioner_type.csv`, `summary_by_state.csv`,
`sample_midlevel_practitioners.csv`, and `sample_midlevel_practitioners.parquet`
(a random 1,000-row subset). Since these files are always small (well under
a megabyte total), `main` just gets a normal incremental commit each month —
no branch squashing or history rewriting needed. Each `manifest.json` records
the full dataset's row count, build timestamp, and duplicate-NPI count, even
though the full data itself never leaves this machine.

## Retention

The last **12** monthly snapshots are kept under `data/processed/` (local
only, full data); older ones are deleted automatically by `build_snapshot.py`
after each run. Change `RETENTION_MONTHS` in that script to adjust. GitHub's
`latest/` always reflects just the current month's example outputs.

## Running manually

```
pip install -r requirements.txt
python3 scripts/run_monthly.py
```

This downloads the current NPPES full replacement file (~1.1GB zip, ~11.7GB
extracted), filters it, writes the full dataset to
`data/processed/<current-YYYY-MM>/` (local only), and pushes the small
`latest/` example (sample + summaries) to GitHub. Takes roughly a few minutes
on a 12-core/24GB machine; scales with source file size and disk/network speed.

## Monthly automation

CMS republishes the full NPPES file on/around the second Monday of each
month. A local cron job runs `scripts/run_monthly.sh` on the **15th of each
month at 06:00** so the dataset stays current without manual action.

Setup (one-time, per machine):

```
cp .env.example .env
# edit .env and set MLP_REPO_DIR to the absolute path of your clone
crontab -e
# add:
0 6 15 * * /absolute/path/to/your/clone/scripts/run_monthly.sh
```

`scripts/run_monthly.sh` reads `MLP_REPO_DIR` from `.env` (gitignored,
machine-specific) and cd's there before running `run_monthly.py` — the
crontab entry itself still needs one absolute path to locate the wrapper
script (cron has no notion of a working directory), but that entry lives
only in your local crontab, never in this repo.

Check `logs/cron_YYYY-MM.log` after the 15th each month to confirm the run
succeeded (or check `latest/manifest.json`'s `built_at_utc`/`row_count`).
