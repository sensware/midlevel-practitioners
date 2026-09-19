# Midlevel Practitioners Dataset

A monthly-refreshed list of active, individually-enumerated U.S. midlevel
practitioners (non-physician clinicians who can see patients and prescribe
medication), built from the CMS NPPES NPI file. Output as CSV, Parquet, and
DuckDB on every run, with the previous 12 monthly snapshots retained.

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
| `enumeration_date`, `last_update_date`, `certification_date` | Record lifecycle dates |
| `is_sole_proprietor` | `Y`/`N` |

NPPES does not include email addresses; there is none in this dataset.

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
scripts/build_snapshot.py        filters/transforms -> csv+parquet+duckdb, archives, prunes
scripts/run_monthly.py           orchestrates the two scripts above; deletes raw download after
data/processed/YYYY-MM/          one dated snapshot per month (csv, parquet, duckdb, manifest.json)
data/current                     symlink to the latest data/processed/YYYY-MM
data/raw/                        scratch space for the ~1.1GB zip / ~11.7GB extracted CSV; NOT retained
```

`data/` and `logs/` are gitignored — only the pipeline code is version
controlled. Each monthly snapshot's `manifest.json` records row count, build
timestamp, and source filename for audit purposes.

## Retention

The last **12** monthly snapshots are kept under `data/processed/`; older
ones are deleted automatically by `build_snapshot.py` after each run.
Change `RETENTION_MONTHS` in that script to adjust.

## Running manually

```
pip install -r requirements.txt
python3 scripts/run_monthly.py
```

This downloads the current NPPES full replacement file (~1.1GB zip, ~11.7GB
extracted), filters it, and writes `data/processed/<current-YYYY-MM>/`. Takes
roughly a few minutes on a 12-core/24GB machine; scales with source file size
and disk/network speed.

## Monthly automation

CMS republishes the full NPPES file on/around the second Monday of each
month. A scheduled cloud agent runs `scripts/run_monthly.py` monthly (see the
`schedule` skill / cron entry associated with this repo) so the dataset
stays current without manual action.
