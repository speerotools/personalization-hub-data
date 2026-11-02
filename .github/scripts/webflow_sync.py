#!/usr/bin/env python3
"""
personalization-hub.json -> Webflow CMS (Personalization Tools + Personalization
Opportunities), plus the landing page's JSON-LD.

Same design as research-hub-data/.github/scripts/webflow_sync.py, so the two
hubs behave alike. The rendering lives in render.py.

How items are matched
---------------------
Every CMS item carries its source id in `airtable-id`: the Airtable record id
once the Airtable sync is live, the hub id (the slug) until then. Matching
falls back to slug, so when record ids arrive the existing items are adopted
and relabelled rather than duplicated.

Tools are written first, because an opportunity's `tools` reference field
needs their Webflow ids.

Safety
------
  - A short data file aborts the run before anything is touched.
  - Removals archive, never delete, and are capped by MAX_ARCHIVE.
  - A changed slug aborts unless ALLOW_SLUG_CHANGE=true (add the 301 first).
  - Item publishing is opt-in (WEBFLOW_PUBLISH). Site publishing is a second,
    separate opt-in, because it pushes every staged change on speero.com.

Environment variables:
  WEBFLOW_TOKEN                      required - CMS read/write + pages + publish
  WEBFLOW_SITE_ID                    default: 5fbb892601063dd93dd166d7
  WEBFLOW_TOOLS_COLLECTION           default: 6ae871c2e332aa28943ce453
  WEBFLOW_OPPORTUNITIES_COLLECTION   default: 6ae871c32b8db33bd1a3cf84
  WEBFLOW_HUB_PAGES                  default: the four hub pages, as key=pageId,...
  DATA_FILE                          default: personalization-hub.json
  ASSET_BASE                         default: the jsDelivr URL of this repo
  WEBFLOW_PUBLISH                    default: "false"
  WEBFLOW_SITE_PUBLISH               default: "false"
  WEBFLOW_CUSTOM_DOMAINS             comma-separated domain ids
  DRY_RUN                            default: "false"
  ALLOW_SLUG_CHANGE                  default: "false"
  MAX_ARCHIVE                        default: "5"
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render  # noqa: E402

API = "https://api.webflow.com/v2"
# Page schema markup is only on the beta API (PATCH /beta/sites/{id}/pages/schema-markup).
BETA_API = "https://api.webflow.com/beta"

TOKEN = os.environ.get("WEBFLOW_TOKEN")
SITE_ID = os.environ.get("WEBFLOW_SITE_ID", "5fbb892601063dd93dd166d7")
TOOLS_COLLECTION = os.environ.get("WEBFLOW_TOOLS_COLLECTION") or "6ae871c2e332aa28943ce453"
OPPS_COLLECTION = os.environ.get("WEBFLOW_OPPORTUNITIES_COLLECTION") or "6ae871c32b8db33bd1a3cf84"
# Hub page ids by section; each gets its own JSON-LD every run.
HUB_PAGES = dict(kv.split("=") for kv in (os.environ.get("WEBFLOW_HUB_PAGES") or
    "home=6ae872418849eb32398047d1,assess=6ae88a25a7d72d7d95fabf58,"
    "opportunities=6ae88a2699cf5a2476b52e00,tools=6ae88a2715066e495041629e").split(","))
DATA_FILE = os.environ.get("DATA_FILE", "personalization-hub.json")
ASSET_BASE = os.environ.get("ASSET_BASE", "https://cdn.jsdelivr.net/gh/speerotools/personalization-hub-data@main/")
PUBLISH = os.environ.get("WEBFLOW_PUBLISH", "false").lower() == "true"
SITE_PUBLISH = os.environ.get("WEBFLOW_SITE_PUBLISH", "false").lower() == "true"
CUSTOM_DOMAINS = [d.strip() for d in os.environ.get("WEBFLOW_CUSTOM_DOMAINS", "").split(",") if d.strip()]
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
ALLOW_SLUG_CHANGE = os.environ.get("ALLOW_SLUG_CHANGE", "false").lower() == "true"
MAX_ARCHIVE = int(os.environ.get("MAX_ARCHIVE", "5"))
MIN_ITEMS = 10  # fewer reads as a failed sync, not a deletion

PURGE_URLS = ["https://purge.jsdelivr.net/gh/speerotools/personalization-hub-data@main/personalization-hub.json"]
BATCH = 100
CHANGED: list[int] = []


def req(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("accept", "application/json")
    if data is not None:
        r.add_header("Content-Type", "application/json")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(r, timeout=45) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code == 429 or e.code >= 500:
                wait = int(e.headers.get("Retry-After") or 2 ** attempt)
                print(f"  {e.code} on {method} {url}; retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"ERROR {e.code} {method} {url}: {detail}", file=sys.stderr)
            raise
        except urllib.error.URLError as e:
            wait = 2 ** attempt
            print(f"  network error {e.reason}; retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"gave up on {method} {url}")


def chunks(seq: list, size: int = BATCH):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def list_items(collection: str) -> list[dict]:
    out, offset = [], 0
    while True:
        res = req("GET", f"{API}/collections/{collection}/items?limit=100&offset={offset}")
        items = res.get("items", [])
        out.extend(items)
        total = (res.get("pagination") or {}).get("total", len(out))
        offset += 100
        if offset >= total or not items:
            break
    return out


def reconcile(label: str, collection: str, desired: dict[str, dict]) -> dict[str, str]:
    """Make the collection match `desired` ({source id: fieldData}).
    Returns {source id: webflow item id}."""
    if len(desired) < MIN_ITEMS:
        print(f"ERROR {label}: only {len(desired)} items in the data file. "
              f"Treating as a failed sync and changing nothing.", file=sys.stderr)
        sys.exit(1)

    print(f"\n== {label}: {len(desired)} items in data")
    existing = list_items(collection) if TOKEN else []
    by_rid = {(i.get("fieldData") or {}).get("airtable-id"): i for i in existing if (i.get("fieldData") or {}).get("airtable-id")}
    by_slug = {(i.get("fieldData") or {}).get("slug"): i for i in existing}

    to_create, to_update, renames, id_map, unchanged = [], [], [], {}, 0
    for rid, fd in desired.items():
        fd = dict(fd, **{"airtable-id": rid})
        item = by_rid.get(rid) or by_slug.get(fd["slug"])
        if not item:
            to_create.append(fd)
            continue
        id_map[rid] = item["id"]
        old = item.get("fieldData") or {}
        if old.get("slug") and old["slug"] != fd["slug"]:
            renames.append(f"{old['slug']} -> {fd['slug']}")
        if old.get("content-hash") == fd["content-hash"] and old.get("airtable-id") == rid:
            unchanged += 1
            continue
        to_update.append({"id": item["id"], "fieldData": fd})

    # An item matched this run (by id or by slug) is never archived, even if
    # its stored airtable-id is an older key, such as the slug it carried
    # before the Airtable record ids arrived. The update relabels it instead.
    matched = set(id_map.values())
    to_archive = [i for i in existing if (i.get("fieldData") or {}).get("airtable-id")
                  and i["id"] not in matched
                  and i["fieldData"]["airtable-id"] not in desired and not i.get("isArchived")]

    if renames and not ALLOW_SLUG_CHANGE:
        print(f"ERROR {label}: slug change(s): {', '.join(renames)}. Add the 301 in Webflow "
              f"site settings first, then re-run with ALLOW_SLUG_CHANGE=true.", file=sys.stderr)
        sys.exit(1)
    if len(to_archive) > MAX_ARCHIVE:
        print(f"ERROR {label}: would archive {len(to_archive)} items (> MAX_ARCHIVE={MAX_ARCHIVE}).", file=sys.stderr)
        sys.exit(1)

    print(f"   plan: {len(to_create)} create, {len(to_update)} update, {unchanged} unchanged, {len(to_archive)} archive")
    if DRY_RUN:
        print("   DRY_RUN: nothing written")
        return id_map

    changed: list[str] = []
    for batch in chunks(to_create):
        res = req("POST", f"{API}/collections/{collection}/items/bulk",
                  {"fieldData": batch, "isDraft": False, "isArchived": False})
        for it in res.get("items", res if isinstance(res, list) else []):
            rid = (it.get("fieldData") or {}).get("airtable-id")
            if rid:
                id_map[rid] = it["id"]
            changed.append(it["id"])
    for batch in chunks(to_update):
        req("PATCH", f"{API}/collections/{collection}/items", {"items": batch})
        changed.extend(u["id"] for u in batch)
    for it in to_archive:
        req("PATCH", f"{API}/collections/{collection}/items/{it['id']}",
            {"isArchived": True, "fieldData": it.get("fieldData") or {}})
        print(f"   archived {(it.get('fieldData') or {}).get('slug')}")

    if PUBLISH and changed:
        for batch in chunks(changed):
            req("POST", f"{API}/collections/{collection}/items/publish", {"itemIds": batch})
        print(f"   published {len(changed)} item(s)")
    elif changed:
        print(f"   {len(changed)} item(s) staged, not published (WEBFLOW_PUBLISH is off)")
    CHANGED.append(len(changed))
    return id_map


def write_hub_schema(data: dict) -> None:
    """Write each hub page's JSON-LD, then check Webflow stored it for every page."""
    res = req("PATCH", f"{BETA_API}/sites/{SITE_ID}/pages/schema-markup",
              {"pages": [{"id": pid, "jsonLdSchema": json.dumps(render.hub_jsonld(data, key), ensure_ascii=False)}
                         for key, pid in HUB_PAGES.items()]})
    stored = {p.get("id") for p in res.get("pages", []) if p.get("jsonLdSchema")}
    missing = [key for key, pid in HUB_PAGES.items() if pid not in stored]
    if missing:
        raise RuntimeError(f"no schema stored for: {', '.join(missing)}")
    print(f"  schema refreshed on {len(HUB_PAGES)} hub pages")


def main() -> None:
    if not TOKEN and not DRY_RUN:
        print("ERROR: WEBFLOW_TOKEN env var required (or DRY_RUN=true)", file=sys.stderr)
        sys.exit(1)
    data = json.loads(Path(DATA_FILE).read_text())

    tools = {}
    for pos, t in enumerate(data["tools"], 1):
        logo = ASSET_BASE + t["logo"] if t.get("logo") else None
        tools[t.get("rid") or t["id"]] = render.tool_fields(t, data, pos, logo)
    tool_ids = reconcile("Personalization Tools", TOOLS_COLLECTION, tools)
    by_hub_id = {t["id"]: tool_ids.get(t.get("rid") or t["id"]) for t in data["tools"]}
    by_hub_id = {k: v for k, v in by_hub_id.items() if v}

    opps = {o.get("rid") or o["id"]: render.opp_fields(o, data, pos, by_hub_id)
            for pos, o in enumerate(data["opportunities"], 1)}
    reconcile("Personalization Opportunities", OPPS_COLLECTION, opps)

    schema_failed = False
    if not DRY_RUN:
        try:
            write_hub_schema(data)
        except Exception as e:  # finish the run, then fail it so the miss is seen
            print(f"ERROR hub page schema update failed: {e}", file=sys.stderr)
            schema_failed = True

    if SITE_PUBLISH and not DRY_RUN and sum(CHANGED):
        body = {"customDomains": CUSTOM_DOMAINS} if CUSTOM_DOMAINS else {"publishToWebflowSubdomain": True}
        req("POST", f"{API}/sites/{SITE_ID}/publish", body)
        print("  site published")

    if not DRY_RUN:
        for u in PURGE_URLS:
            try:
                urllib.request.urlopen(u, timeout=30).read()
            except Exception as e:
                print(f"  WARN purge failed for {u}: {e}", file=sys.stderr)
    if schema_failed:
        sys.exit(1)
    print("\nDone.")


if __name__ == "__main__":
    main()
