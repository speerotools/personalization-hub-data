#!/usr/bin/env python3
"""Airtable -> personalization-hub.json.

Source of truth: Nick's Personalization Hub base, appulGzKcE8TQIO70.

Status: the base's tables and fields have not been confirmed yet (the
ClickUp assessment asks for exactly that before migration). Until they are,
this script keeps the site on the prototype dataset by running build.py, and
says so loudly in the log. The output shape does not change when the
Airtable reader lands, so the embed and webflow_sync.py are unaffected.

    python .github/scripts/sync.py            # build personalization-hub.json
    python .github/scripts/sync.py --schema   # print the base's tables and fields

Finishing the Airtable reader:
  1. Run --schema with AIRTABLE_TOKEN set and map each table to the JSON keys
     in build.py (opportunities, tools, pillars/questions, levels, library).
  2. Fill TABLES below and implement read_airtable() to return the same dict
     build.py writes, carrying each record id as "rid" on opportunities and
     tools so webflow_sync.py can join on it.
  3. Set the repo variable AIRTABLE_MAPPED=true.

Environment variables:
  AIRTABLE_TOKEN     PAT with data.records:read + schema.bases:read on the base
  AIRTABLE_BASE      default: appulGzKcE8TQIO70
  AIRTABLE_MAPPED    "true" once read_airtable() is implemented
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
BASE = os.environ.get("AIRTABLE_BASE", "appulGzKcE8TQIO70")
TOKEN = os.environ.get("AIRTABLE_TOKEN")
MAPPED = os.environ.get("AIRTABLE_MAPPED", "false").lower() == "true"

TABLES: dict[str, str] = {}  # json key -> Airtable table name, filled after --schema


def api(path: str) -> dict:
    r = urllib.request.Request("https://api.airtable.com/v0/" + path)
    r.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(r, timeout=45) as resp:
        return json.loads(resp.read().decode())


def print_schema() -> None:
    for t in api(f"meta/bases/{BASE}/tables")["tables"]:
        print(f"\n{t['name']}  ({t['id']})")
        for f in t["fields"]:
            print(f"   {f['name']:<40} {f['type']}")


def read_airtable() -> dict:
    raise NotImplementedError("Map the Airtable tables first: see the docstring.")


def main() -> None:
    if "--schema" in sys.argv:
        if not TOKEN:
            sys.exit("AIRTABLE_TOKEN is required for --schema")
        print_schema()
        return
    if TOKEN and MAPPED:
        data = read_airtable()
        Path("personalization-hub.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        return
    print("::warning::Airtable mapping not confirmed yet; building from the prototype dataset (source/prototype-extract.json).")
    subprocess.run([sys.executable, str(HERE / "build.py")], check=True)


if __name__ == "__main__":
    main()
