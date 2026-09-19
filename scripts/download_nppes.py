#!/usr/bin/env python3
"""Download the current NPPES Full Replacement Monthly NPI File.

CMS republishes this file every month under a new filename (e.g.
NPPES_Data_Dissemination_September_2026_V2.zip), so we scrape the stable
anchor id 'DDSMTH.ZIP.D' on the NPI Files page rather than hardcoding a URL.
"""
import re
import sys
import urllib.request
from pathlib import Path

NPI_FILES_PAGE = "https://download.cms.gov/nppes/NPI_Files.html"
LINK_ID = "DDSMTH.ZIP.D"
USER_AGENT = "Mozilla/5.0 (Midlevel-Practitioners-Pipeline)"


def find_monthly_zip_url() -> str:
    req = urllib.request.Request(NPI_FILES_PAGE, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    match = re.search(rf"id=['\"]{re.escape(LINK_ID)}['\"]\s+href=['\"]([^'\"]+)['\"]", html)
    if not match:
        raise RuntimeError(
            f"Could not find monthly NPI file link (id={LINK_ID}) on {NPI_FILES_PAGE}. "
            "CMS may have changed the page layout."
        )
    relative_url = match.group(1)
    return urllib.request.urljoin(NPI_FILES_PAGE, relative_url)


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    interactive = sys.stdout.isatty()
    last_reported_pct = -1
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        written = 0
        chunk = 1024 * 1024
        while True:
            block = resp.read(chunk)
            if not block:
                break
            out.write(block)
            written += len(block)
            if not total:
                continue
            pct = written / total * 100
            if interactive:
                print(f"\r  {written/1e6:,.0f} MB / {total/1e6:,.0f} MB ({pct:.1f}%)", end="", flush=True)
            elif int(pct // 10) > last_reported_pct:
                last_reported_pct = int(pct // 10)
                print(f"  {written/1e6:,.0f} MB / {total/1e6:,.0f} MB ({pct:.0f}%)", flush=True)
    print()
    tmp.rename(dest)
    return dest


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw/npppes_download.zip")
    url = find_monthly_zip_url()
    print(f"Source URL: {url}")
    print(f"Downloading to: {out_path}")
    download(url, out_path)
    print("Download complete.")
    print(url.rsplit("/", 1)[-1])  # last line: source filename, used by build_snapshot.py


if __name__ == "__main__":
    main()
