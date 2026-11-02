"""Builds personalization-hub.json, the one file the embed reads.

Today the input is source/prototype-extract.json: the content of Nick's
prototype, pulled from its deployed bundle by extract_prototype.py. When the
Airtable base is confirmed, a sync.py that reads Airtable replaces that input
and this file keeps the same output shape, so the embed does not change.

    python3 .github/scripts/build.py
"""
import json, os, sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = json.load(open(os.path.join(ROOT, "source", "prototype-extract.json")))

STAGE_COLOR = {"acq": "#001641", "disc": "#480F43", "conv": "#FF0049",
               "act": "#FFB800", "ret": "#3D5273", "exp": "#805779"}

def stage(s):
    key = s["token"].replace("bg-stage-", "")
    return {"id": s["id"], "label": s["label"], "color": STAGE_COLOR[key]}

def strip(o, drop):
    return {k: v for k, v in o.items() if k not in drop}

tools = src["index.gy"]
logos = set(f[:-4] for f in os.listdir(os.path.join(ROOT, "logos")) if f.endswith(".png"))
for t in tools:
    t["logo"] = f"logos/{t['id']}.png" if t["id"] in logos else None

opps = src["index.py"]
for o in opps:
    o["format"] = src["_id.g"].get(o["id"])  # the highlighted example format in step 4
pillar_detail = {p["id"]: p["detail"] for p in src["program.f"]}
for p in src["index.Fv"]:
    p["detail"] = pillar_detail[p["id"]]
library = src["library.e"] + src["library.t"] + src["library.n"]

data = {
    "version": 1,
    "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "source": "prototype",
    "taxonomy": {
        "models": src["catalog.e"],
        "needs": src["catalog.r"],
        "stages": [stage(s) for s in src["catalog.i"]],
        "intents": src["catalog.n"],
        "signals": src["catalog.t"],
        "roles": src["catalog.a"],
        "arms": src["_id._"],
        "answers": src["index.Mv"],
    },
    "steps": src["framework.e"],
    "pillars": [strip(p, ()) for p in src["index.Fv"]],
    "levels": src["index.zv"],
    "opportunities": opps,
    "tools": tools,
    "library": library,
    "myths": src["research.n"],
    "roadmap": src["catalog.o"],
}

# Referential checks: a broken id should stop the build, not ship a dead link.
ids = {"opp": {o["id"] for o in opps}, "tool": {t["id"] for t in tools}, "lib": {l["id"] for l in library}}
tax = {k: {x["id"] for x in v} for k, v in data["taxonomy"].items() if k not in ("arms", "answers")}
errors = []
for o in opps:
    for r in o["related"]:
        if r not in ids["opp"]: errors.append(f"opportunity {o['id']}: related '{r}' not found")
    for r in o["toolIds"]:
        if r not in ids["tool"]: errors.append(f"opportunity {o['id']}: tool '{r}' not found")
    if o["stage"] not in tax["stages"]: errors.append(f"opportunity {o['id']}: stage '{o['stage']}'")
    if o["situation"] not in tax["needs"]: errors.append(f"opportunity {o['id']}: need '{o['situation']}'")
    for m in o["models"]:
        if m not in tax["models"]: errors.append(f"opportunity {o['id']}: model '{m}'")
for t in tools:
    if t["role"] not in tax["roles"]: errors.append(f"tool {t['id']}: role '{t['role']}'")
    for a in t["applicationIds"]:
        if a not in ids["lib"]: errors.append(f"tool {t['id']}: application '{a}' not found")
if sum(len(p["items"]) for p in data["pillars"]) * 2 != data["levels"][-1]["max"]:
    errors.append("level bands do not match question count")
if errors:
    print("\n".join(errors)); sys.exit(1)

out = os.path.join(ROOT, "personalization-hub.json")
json.dump(data, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
print(f"{len(opps)} opportunities, {len(tools)} tools, {len(library)} library entries, "
      f"{sum(len(p['items']) for p in data['pillars'])} questions -> {os.path.getsize(out)} bytes")
