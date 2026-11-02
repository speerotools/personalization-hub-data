#!/usr/bin/env python3
"""Airtable -> personalization-hub.json.

Source of truth: Nick's Personalization Hub base, appulGzKcE8TQIO70. The
table map below was written from airtable-schema.json.

    python .github/scripts/sync.py            # build personalization-hub.json
    python .github/scripts/sync.py --schema   # record the base's tables and fields
    python .github/scripts/sync.py --check    # read Airtable, compare with the prototype, write nothing

While AIRTABLE_MAPPED is off, a run with a token reads Airtable, validates it
and logs how it differs from the prototype dataset, then still publishes the
prototype dataset. Turn AIRTABLE_MAPPED on once that comparison looks right.

The logs of this public repo are public, so the comparison names slugs and
field names only, never values.

Table map
  Opportunities          -> opportunities   (select values resolved through Taxonomy)
  Tools                  -> tools           (Profile Applications -> applicationIds)
  Applications, Concepts, Practices -> library
  Myths                  -> myths
  Framework Steps        -> steps
  Program Pillars + Audit Questions -> pillars and their questions
  Audit Score Bands      -> levels
  Audit Answer Levels    -> taxonomy.answers
  Taxonomy               -> taxonomy.models / needs / stages / intents / signals
Not read: Plays, Audit Groups (the earlier audit), the legacy score fields.
Kept from the prototype because the base has no table for them: stack role
ids, the Assist / Adapt / Transform labels, stage colours, the twelve-week
roadmap on the blueprints page.

Environment variables:
  AIRTABLE_TOKEN     PAT with data.records:read + schema.bases:read on the base
  AIRTABLE_BASE      default: appulGzKcE8TQIO70
  AIRTABLE_MAPPED    "true" publishes the Airtable data instead of the prototype
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402

BASE = os.environ.get("AIRTABLE_BASE", "appulGzKcE8TQIO70")
TOKEN = os.environ.get("AIRTABLE_TOKEN")
MAPPED = os.environ.get("AIRTABLE_MAPPED", "false").lower() == "true"

INACTIVE = re.compile(r"legacy|archiv|inactive|retired|draft|hidden|deprecated", re.I)
TAX_TYPE = [("model", "models"), ("business", "models"), ("situation", "needs"), ("need", "needs"),
            ("stage", "stages"), ("intent", "intents"), ("context", "signals"), ("signal", "signals")]
STAGE_COLOR = {"acquisition": "#001641", "discovery": "#480F43", "conversion": "#FF0049",
               "activation": "#FFB800", "retention": "#3D5273", "expansion": "#805779"}


def api(path: str) -> dict:
    r = urllib.request.Request("https://api.airtable.com/v0/" + path)
    r.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(r, timeout=45) as resp:
        return json.loads(resp.read().decode())


def count_records(table_id: str, primary_field_id: str) -> int:
    # Fetch only the primary field: the smallest request Airtable accepts
    # (an empty fields[] is a 422). The values are counted, never printed.
    n, offset = 0, None
    while True:
        q = f"pageSize=100&returnFieldsByFieldId=true&fields%5B%5D={primary_field_id}"
        res = api(f"{BASE}/{table_id}?{q}" + (f"&offset={offset}" if offset else ""))
        n += len(res.get("records", []))
        offset = res.get("offset")
        if not offset:
            return n


def print_schema() -> None:
    """Writes the base's structure to airtable-schema.json and the log: table
    and field names, types, how many choices a select has, and record counts.
    This repo and its Actions logs are public, so choice values, view names
    and record content are never printed or written. Run it locally if you
    need those."""
    tables = api(f"meta/bases/{BASE}/tables")["tables"]
    out = []
    for t in tables:
        n = count_records(t["id"], t["primaryFieldId"])
        print(f"\n{t['name']}  ({t['id']}, {n} records, {len(t.get('views', []))} views)")
        fields = []
        for f in t["fields"]:
            opts = f.get("options") or {}
            choices = [c["name"] for c in opts.get("choices", [])]
            print(f"   {f['name']:<40} {f['type']}" + (f"  ({len(choices)} choices)" if choices else ""))
            fields.append({k: v for k, v in {
                "name": f["name"], "type": f["type"],
                "choiceCount": len(choices) or None,
                "linkedTable": opts.get("linkedTableId"),
            }.items() if v})
        out.append({"name": t["name"], "id": t["id"], "records": n,
                    "viewCount": len(t.get("views", [])), "fields": fields})
    Path("airtable-schema.json").write_text(json.dumps({"base": BASE, "tables": out}, indent=1, ensure_ascii=False))


class Problems(list):
    """Collects what the Airtable data cannot be mapped into, with record
    slugs and field names only."""
    def add(self, where, msg):
        self.append(f"{where}: {msg}")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def lines(text):
    """Multiline text -> list items, without bullets or numbering."""
    out = []
    for ln in str(text or "").splitlines():
        ln = re.sub(r"^\s*(?:[-*\u2022\u2013]|\d+[.)])\s*", "", ln).strip()
        if ln:
            out.append(ln)
    return out


def text(f, name):
    return str(f.get(name) or "").strip()


def read_tables() -> dict:
    """{table name: [records]} in each table's first-view order."""
    out = {}
    for t in api(f"meta/bases/{BASE}/tables")["tables"]:
        view = (t.get("views") or [{}])[0].get("id")
        recs, offset = [], None
        while True:
            q = {"pageSize": 100}
            if view:
                q["view"] = view
            if offset:
                q["offset"] = offset
            res = api(f"{BASE}/{t['id']}?" + urllib.parse.urlencode(q))
            recs += res.get("records", [])
            offset = res.get("offset")
            if not offset:
                break
        out[t["name"]] = recs
    return out


def active(rec):
    return not INACTIVE.search(str(rec["fields"].get("Status") or ""))


def by_order(recs):
    return sorted(recs, key=lambda r: (r["fields"].get("Order") is None, r["fields"].get("Order") or 0))


def read_airtable(tables: dict, problems: Problems) -> dict:
    proto = build.prototype_data()
    slug_of = {r["id"]: text(r["fields"], "Slug") for recs in tables.values() for r in recs}
    links = lambda f, name: [slug_of[i] for i in f.get(name) or [] if slug_of.get(i)]

    # Taxonomy: one table for five option lists. "Select Option" is the
    # value used in the select fields elsewhere; Label is what the hub shows.
    tax = {k: [] for k in ("models", "needs", "stages", "intents", "signals")}
    choice = {k: {} for k in tax}
    for r in by_order(tables.get("Taxonomy", [])):
        f = r["fields"]
        kind = next((k for word, k in TAX_TYPE if word in str(f.get("Type") or "").lower()), None)
        if not kind:
            problems.add(f"Taxonomy {text(f, 'Slug')}", "Type matches none of the five lists")
            continue
        row = {"id": text(f, "Slug"), "label": text(f, "Label")}
        if text(f, "Blurb"):
            row["blurb"] = text(f, "Blurb")
        if kind == "stages":
            row["color"] = STAGE_COLOR.get(row["id"], "#001641")
        tax[kind].append(row)
        for v in (f.get("Select Option"), f.get("Label"), f.get("Slug")):
            if v:
                choice[kind][str(v).strip().lower()] = row["id"]

    def pick(kind, value, where, field):
        if value in (None, ""):
            return None
        hit = choice[kind].get(str(value).strip().lower())
        if not hit:
            problems.add(where, f"a {field} choice has no Taxonomy row")
        return hit

    signal_label = {r["label"].lower(): r["id"] for r in tax["signals"]}

    def signals(f, contexts, where):
        out = []
        for ln in lines(f.get("Signals")):
            m = re.match(r"^([A-Za-z]+)\s*[:\u2014\u2013-]\s*(.+)$", ln)
            kind = signal_label.get(m.group(1).lower()) if m else None
            if kind:
                out.append({"kind": kind, "example": m.group(2).strip()})
            else:
                if not contexts:
                    problems.add(where, "a Signals line names no signal type and the record has no Contexts")
                out.append({"kind": contexts[0] if contexts else "inferred", "example": ln})
        return out

    opps = []
    for r in by_order(tables.get("Opportunities", [])):
        f = r["fields"]
        w = f"Opportunity {text(f, 'Slug') or r['id']}"
        contexts = [c for c in (pick("signals", v, w, "Contexts") for v in f.get("Contexts") or []) if c]
        o = {
            "id": text(f, "Slug"), "rid": r["id"], "title": text(f, "Title"),
            "situation": pick("needs", f.get("Situation"), w, "Situation"),
            "stage": pick("stages", f.get("Stage"), w, "Stage"),
            "contexts": contexts,
            "intents": [c for c in (pick("intents", v, w, "Intents") for v in f.get("Intents") or []) if c],
            "models": [c for c in (pick("models", v, w, "Business Models") for v in f.get("Business Models") or []) if c],
            "summary": text(f, "Summary"), "whatsGoingOn": text(f, "What's Going On"),
            "whyItEarns": text(f, "Why It Earns Complexity"), "confusion": text(f, "Confusion To Avoid"),
            "signals": signals(f, contexts, w), "eligibilityRule": text(f, "Eligibility Rule"),
            "arms": {"low": text(f, "Response \u2014 Assist"), "medium": text(f, "Response \u2014 Adapt"),
                     "high": text(f, "Response \u2014 Transform")},
            "test": {"control": text(f, "Test Control"), "treatment": text(f, "Test Treatment"),
                     "primaryMetric": text(f, "Primary Metric"), "guardrail": text(f, "Guardrail")},
            "pitfalls": lines(f.get("Pitfalls")),
            "toolIds": links(f, "Tools"), "related": links(f, "Related Opportunities"),
            "format": text(f, "Response Format") or None,
        }
        if text(f, "Test Audience Readout"):
            o["test"]["audienceReadout"] = text(f, "Test Audience Readout")
        opps.append(o)

    roles = list(proto["taxonomy"]["roles"])
    role_id = {x["label"].lower(): x["id"] for x in roles}
    have_logo = build.logos()
    tools = []
    for r in tables.get("Tools", []):
        f = r["fields"]
        label = text(f, "Stack Role")
        if label and label.lower() not in role_id:
            role_id[label.lower()] = slugify(label)
            roles.append({"id": slugify(label), "label": label})
        apps = links(f, "Profile Applications")
        t = {
            "id": text(f, "Slug"), "rid": r["id"], "name": text(f, "Name"), "role": role_id.get(label.lower(), ""),
            "summary": text(f, "Summary"),
            # Hand-written in the base ("Supporting data layer" on data tools),
            # so it is read, and only counted when the field is empty.
            "connected": text(f, "Connected Data") or f"{len(apps)} connected application{'' if len(apps) == 1 else 's'}",
            "models": [c for c in (pick("models", v, f"Tool {text(f, 'Slug')}", "Business Models")
                                   for v in f.get("Business Models") or []) if c],
            "strengths": lines(f.get("Strengths")), "limits": lines(f.get("Limits")),
            "bestFor": text(f, "Best For"), "questions": lines(f.get("Questions To Ask")),
            "applicationIds": apps,
            "source": {"url": text(f, "Source URL"), "claim": text(f, "Source Claim")} if text(f, "Source URL") else None,
        }
        t["logo"] = f"logos/{t['id']}.png" if t["id"] in have_logo else None
        if not t["logo"]:
            # Not a blocker: the embed shows the tool's initial instead.
            print(f"  note: Tool {t['id']} has no logos/{t['id']}.png")
        tools.append(t)

    library = []
    for table, kind in (("Applications", "application"), ("Concepts", "concept"), ("Practices", "practice")):
        for r in tables.get(table, []):
            f = r["fields"]
            library.append({
                "id": text(f, "Slug"), "kind": kind, "name": text(f, "Name"),
                "summary": text(f, "Summary"), "body": text(f, "Body"),
                "models": [c for c in (pick("models", v, f"{table} {text(f, 'Slug')}", "Business Models")
                                       for v in f.get("Business Models") or []) if c],
                "relatedOpportunityIds": links(f, "Related Opportunities"),
                "relatedToolIds": links(f, "Related Tools"),
                "tags": [x.strip() for x in re.split(r"[,\n]", text(f, "Tags")) if x.strip()],
            })

    # Steps and pillars keep the prototype ids where the names match, because
    # the embed draws an icon per id.
    proto_step = {s["label"].lower(): s["id"] for s in proto["steps"]}
    steps = [{"id": proto_step.get(text(r["fields"], "Name").lower(), text(r["fields"], "Slug")),
              "label": text(r["fields"], "Name"), "question": text(r["fields"], "Question"),
              "summary": text(r["fields"], "Summary"), "detail": text(r["fields"], "Description")}
             for r in by_order(tables.get("Framework Steps", [])) if active(r)]

    questions = by_order([r for r in tables.get("Audit Questions", []) if active(r)])
    proto_pillar = {p["label"].lower(): p["id"] for p in proto["pillars"]}
    pillars = []
    for r in by_order(tables.get("Program Pillars", [])):
        if not active(r):
            continue
        f = r["fields"]
        pillars.append({
            "id": proto_pillar.get(text(f, "Name").lower(), text(f, "Slug")),
            "label": text(f, "Name"), "question": text(f, "Question"),
            "kicker": text(f, "Description"), "detail": text(f, "Description"),
            "items": [{"id": text(q["fields"], "Slug"), "text": text(q["fields"], "Question"),
                       "example": text(q["fields"], "Example"), "action": text(q["fields"], "Recommended Action"),
                       "guidance": text(q["fields"], "Guidance")}
                      for q in questions if r["id"] in (q["fields"].get("Program Pillar") or [])],
        })

    levels = sorted(({"id": text(r["fields"], "Slug"), "min": r["fields"].get("Min"), "max": r["fields"].get("Max"),
                      "bars": r["fields"].get("Bars"), "label": text(r["fields"], "Label"),
                      "blurb": text(r["fields"], "Blurb")} for r in tables.get("Audit Score Bands", [])),
                    key=lambda x: x["min"] or 0)
    answers = [{"id": text(r["fields"], "Slug"), "label": text(r["fields"], "Label"), "points": r["fields"].get("Points")}
               for r in by_order(tables.get("Audit Answer Levels", []))]
    myths = [{"id": text(r["fields"], "Slug"), "claim": text(r["fields"], "Claim"),
              "truth": text(r["fields"], "Truth"), "detail": text(r["fields"], "Detail")}
             for r in tables.get("Myths", [])]

    known_steps = {s["id"] for s in proto["steps"]}
    for s in steps:
        if s["id"] not in known_steps:
            problems.add(f"Framework step {s['id']}", "not one of the five steps the embed draws")
    for p in pillars:
        if p["id"] not in proto_pillar.values():
            problems.add(f"Program pillar {p['id']}", "not one of the four pillars the embed draws")
    if {a["id"] for a in answers} != {"not-yet", "some", "consistently"}:
        problems.add("Audit Answer Levels", "slugs differ from not-yet / some / consistently, which the scoring uses")

    taxonomy = dict(tax, roles=roles, arms=proto["taxonomy"]["arms"], answers=answers)
    return {"version": 1, "source": "airtable", "taxonomy": taxonomy, "steps": steps, "pillars": pillars,
            "levels": levels, "opportunities": opps, "tools": tools, "library": library, "myths": myths,
            "roadmap": proto["roadmap"]}


def compare(at: dict, proto: dict) -> list[str]:
    """How the Airtable read differs from the prototype dataset: counts, slugs
    present on one side only, and for matching slugs the names of the fields
    whose values differ. No values, because this goes to the public log and to
    airtable-compare.txt."""
    out = []
    print = out.append  # noqa: A001  collect, then the caller prints and saves
    def rows(d):
        return {
            "opportunities": d["opportunities"], "tools": d["tools"], "library": d["library"],
            "myths": d["myths"], "steps": d["steps"], "pillars": d["pillars"], "levels": d["levels"],
            "questions": [q for p in d["pillars"] for q in p["items"]],
            **{f"taxonomy.{k}": d["taxonomy"][k] for k in ("models", "needs", "stages", "intents", "signals", "answers")},
        }
    a, p = rows(at), rows(proto)
    print("\nAirtable vs prototype")
    for k in p:
        ai = {r["id"]: r for r in a[k]}
        pi = {r["id"]: r for r in p[k]}
        diffs = {}
        for i in ai.keys() & pi.keys():
            fields = sorted(x for x in (ai[i].keys() | pi[i].keys()) - {"rid", "items"}
                            if ai[i].get(x) != pi[i].get(x))
            for x in fields:
                diffs.setdefault(x, []).append(i)
        print(f"  {k}: {len(a[k])} in Airtable, {len(p[k])} in the prototype")
        if ai.keys() - pi.keys():
            print(f"    only in Airtable: {', '.join(sorted(ai.keys() - pi.keys()))}")
        if pi.keys() - ai.keys():
            print(f"    only in the prototype: {', '.join(sorted(pi.keys() - ai.keys()))}")
        for x, ids in sorted(diffs.items()):
            print(f"    '{x}' differs on {len(ids)}: {', '.join(sorted(ids)[:8])}{' ...' if len(ids) > 8 else ''}")
        same_order = [r["id"] for r in a[k] if r["id"] in pi] == [r["id"] for r in p[k] if r["id"] in ai]
        if not same_order:
            print("    order differs")
    return out


def from_airtable():
    problems = Problems()
    data = read_airtable(read_tables(), problems)
    for msg in problems:
        print(f"  problem: {msg}")
    return data, problems


def main() -> None:
    if "--schema" in sys.argv:
        if not TOKEN:
            sys.exit("AIRTABLE_TOKEN is required for --schema")
        print_schema()
        return
    if "--check" in sys.argv or (TOKEN and not MAPPED):
        if not TOKEN:
            sys.exit("AIRTABLE_TOKEN is required for --check")
        data, problems = from_airtable()
        report = compare(data, build.prototype_data())
        report += [f"  problem: {m}" for m in problems]
        try:
            build.validate(data)
            report.append("\nAirtable data passes validation." + (" Mapping problems listed above." if problems else ""))
        except SystemExit:
            report.append("\nAirtable data fails validation (see the run log).")
        print("\n".join(report))
        Path("airtable-compare.txt").write_text("\n".join(report).lstrip() + "\n")
        if "--check" in sys.argv:
            return
    if TOKEN and MAPPED:
        data, problems = from_airtable()
        if problems:
            sys.exit("Airtable mapping problems above: nothing written.")
        build.validate(data)
        build.write(data)
        return
    print("::warning::Publishing the prototype dataset (AIRTABLE_MAPPED is off). "
          "The Airtable comparison above shows what would change.")
    d = build.prototype_data()
    build.validate(d)
    build.write(d)


if __name__ == "__main__":
    main()
