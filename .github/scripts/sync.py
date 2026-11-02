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


def count_records(table_id: str) -> int:
    n, offset = 0, None
    while True:
        res = api(f"{BASE}/{table_id}?pageSize=100&fields%5B%5D=" + ("&offset=" + offset if offset else ""))
        n += len(res.get("records", []))
        offset = res.get("offset")
        if not offset:
            return n


def print_schema() -> None:
    """Writes the base's structure to airtable-schema.json: table and field
    names, types, how many choices a select has, and record counts. This repo
    is public, so choice values and view names go to the job log only, which
    needs repo access to read."""
    tables = api(f"meta/bases/{BASE}/tables")["tables"]
    out = []
    for t in tables:
        n = count_records(t["id"])
        print(f"\n{t['name']}  ({t['id']}, {n} records)  views: {', '.join(v['name'] for v in t.get('views', []))}")
        fields = []
        for f in t["fields"]:
            opts = f.get("options") or {}
            choices = [c["name"] for c in opts.get("choices", [])]
            print(f"   {f['name']:<40} {f['type']}" + (f"  [{', '.join(choices)}]" if choices else ""))
            fields.append({k: v for k, v in {
                "name": f["name"], "type": f["type"],
                "choiceCount": len(choices) or None,
                "linkedTable": opts.get("linkedTableId"),
            }.items() if v})
        out.append({"name": t["name"], "id": t["id"], "records": n,
                    "viewCount": len(t.get("views", [])), "fields": fields})
    Path("airtable-schema.json").write_text(json.dumps({"base": BASE, "tables": out}, indent=1, ensure_ascii=False))


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
