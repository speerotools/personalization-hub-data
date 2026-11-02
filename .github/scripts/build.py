"""Builds personalization-hub.json, the one file the embed reads.

Two sources produce the same shape:
  - prototype_data(): source/prototype-extract.json, the content of Nick's
    prototype pulled from its deployed bundle by extract_prototype.py.
  - sync.read_airtable(): Nick's Airtable base, once AIRTABLE_MAPPED is on.

Both go through validate() and write(), so a broken reference stops the run
whichever source it came from.

    python3 .github/scripts/build.py
"""
import json, os, re, sys
from datetime import datetime, timezone
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "personalization-hub.json")

STAGE_COLOR = {"acq": "#001641", "disc": "#480F43", "conv": "#FF0049",
               "act": "#FFB800", "ret": "#3D5273", "exp": "#805779"}


def load_prototype():
    return json.load(open(os.path.join(ROOT, "source", "prototype-extract.json")))


def logos():
    return set(f[:-4] for f in os.listdir(os.path.join(ROOT, "logos")) if f.endswith(".png"))


def stage(s):
    key = s["token"].replace("bg-stage-", "")
    return {"id": s["id"], "label": s["label"], "color": STAGE_COLOR[key]}


def prototype_data():
    src = load_prototype()
    have = logos()
    tools = src["index.gy"]
    for t in tools:
        t["logo"] = f"logos/{t['id']}.png" if t["id"] in have else None
    opps = src["index.py"]
    for o in opps:
        o["format"] = src["_id.g"].get(o["id"])  # the highlighted example format in step 4
    pillar_detail = {p["id"]: p["detail"] for p in src["program.f"]}
    for p in src["index.Fv"]:
        p["detail"] = pillar_detail[p["id"]]
    return {
        "version": 1,
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
        "pillars": src["index.Fv"],
        "levels": src["index.zv"],
        "opportunities": opps,
        "tools": tools,
        "library": src["library.e"] + src["library.t"] + src["library.n"],
        "myths": src["research.n"],
        "roadmap": src["catalog.o"],
    }


SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate(data):
    """Referential checks: a broken id should stop the build, not ship a dead link.

    Ids end up in URLs and href attributes on speero.com, and source URLs in
    links, so both are held to a strict shape: slugs are lowercase words and
    hyphens, source URLs are absolute http(s). Anything else fails the run."""
    opps, tools, library = data["opportunities"], data["tools"], data["library"]
    ids = {"opp": {o["id"] for o in opps}, "tool": {t["id"] for t in tools}, "lib": {l["id"] for l in library}}
    tax = {k: {x["id"] for x in v} for k, v in data["taxonomy"].items() if k not in ("arms", "answers")}
    errors = []
    id_rows = [("opportunity", opps), ("tool", tools), ("library entry", library), ("myth", data["myths"]),
               ("step", data["steps"]), ("pillar", data["pillars"]), ("level", data["levels"]),
               ("question", [q for p in data["pillars"] for q in p["items"]])]
    id_rows += [(f"taxonomy {k}", v) for k, v in data["taxonomy"].items() if k != "arms"]
    for kind, rows in id_rows:
        for r in rows:
            if r.get("id") and not SLUG.match(str(r["id"])):
                errors.append(f"{kind} slug is not lowercase words and hyphens (record {r.get('rid') or 'unknown'})")
    for t in tools:
        url = (t.get("source") or {}).get("url")
        if url:
            u = urlparse(url)
            if u.scheme not in ("http", "https") or not u.netloc:
                errors.append(f"tool {t['id']}: Source URL is not an absolute http(s) link")
    for kind, rows in (("opportunity", opps), ("tool", tools), ("library entry", library)):
        seen = set()
        for r in rows:
            if not r.get("id"):
                errors.append(f"{kind} '{r.get('title') or r.get('name')}': no slug")
            elif r["id"] in seen:
                errors.append(f"{kind} {r['id']}: duplicate slug")
            seen.add(r.get("id"))
    for o in opps:
        for r in o["related"]:
            if r not in ids["opp"]: errors.append(f"opportunity {o['id']}: related '{r}' not found")
        for r in o["toolIds"]:
            if r not in ids["tool"]: errors.append(f"opportunity {o['id']}: tool '{r}' not found")
        if o["stage"] not in tax["stages"]: errors.append(f"opportunity {o['id']}: stage '{o['stage']}'")
        if o["situation"] not in tax["needs"]: errors.append(f"opportunity {o['id']}: need '{o['situation']}'")
        for k, t in (("models", "models"), ("intents", "intents"), ("contexts", "signals")):
            for m in o[k]:
                if m not in tax[t]: errors.append(f"opportunity {o['id']}: {k[:-1]} '{m}'")
        for s in o["signals"]:
            if s["kind"] not in tax["signals"]: errors.append(f"opportunity {o['id']}: signal kind '{s['kind']}'")
        if not o["arms"].get("medium"): errors.append(f"opportunity {o['id']}: no Adapt response")
    for t in tools:
        if t["role"] not in tax["roles"]: errors.append(f"tool {t['id']}: role '{t['role']}'")
        for a in t["applicationIds"]:
            if a not in ids["lib"]: errors.append(f"tool {t['id']}: application '{a}' not found")
    for p in data["pillars"]:
        if not p["items"]: errors.append(f"pillar {p['id']}: no questions")
    if sum(len(p["items"]) for p in data["pillars"]) * 2 != data["levels"][-1]["max"]:
        errors.append("level bands do not match question count")
    if len(opps) < 10 or len(tools) < 10:
        errors.append(f"only {len(opps)} opportunities and {len(tools)} tools: reads as a failed read, not a deletion")
    if errors:
        print("\n".join(errors))
        sys.exit(1)


def write(data):
    data = dict(data, generatedAt=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    json.dump(data, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"{len(data['opportunities'])} opportunities, {len(data['tools'])} tools, "
          f"{len(data['library'])} library entries, {sum(len(p['items']) for p in data['pillars'])} questions "
          f"from {data['source']} -> {os.path.getsize(OUT)} bytes")


if __name__ == "__main__":
    d = prototype_data()
    validate(d)
    write(d)
