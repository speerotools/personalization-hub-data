"""Pure functions: personalization-hub.json -> Webflow CMS field data and JSON-LD.
No network. webflow_sync.py calls these; so does the first load.

Every heading the template shows comes from the prototype's opportunity and
tool pages, so a CMS page reads the same as the embed's view of that item.
"""
import hashlib
import html
import json

SITE = "https://speero.com"
HUB = "/personalization-hub"
OPP_BASE = "/personalization-opportunities/"
TOOL_BASE = "/personalization-tools/"
FORMATS = ["Content", "Experience", "Sequence", "Recommendations"]

e = lambda s: html.escape(str(s or ""), quote=False)
attr = lambda s: html.escape(str(s or ""), quote=True)  # attribute values


def labels(data):
    return {k: {x["id"]: x["label"] for x in v} for k, v in data["taxonomy"].items() if k not in ("arms", "answers")}


def ul(items):
    return "<ul>" + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>" if items else ""


def clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def meta_title(name, suffix, limit=70):
    """Drop the suffix, then the brand, before cutting the name itself:
    a title clipped mid-phrase reads worse in results than a shorter one."""
    for tail in (suffix, " | Speero", ""):
        if len(name + tail) <= limit:
            return name + tail
    return clip(name, limit)


def content_hash(fields):
    return hashlib.sha1(json.dumps(fields, sort_keys=True).encode()).hexdigest()[:16]


def tool_fields(t, data, order, logo_url=None):
    L = labels(data)
    opps = {o["id"]: o for o in data["opportunities"]}
    lib = {l["id"]: l for l in data["library"]}
    apps = []
    for a in t["applicationIds"]:
        l = lib.get(a)
        if not l:
            continue
        op = opps.get((l["relatedOpportunityIds"] or [None])[0])
        link = f'<p><a href="{attr(OPP_BASE + op["id"])}">{e(op["title"])}</a></p>' if op else ""
        apps.append(f"<h3>{e(l['name'])}</h3><p>{e(l['summary'])}</p>{link}")
    f = {
        "name": t["name"],
        "slug": t["id"],
        "stack-role": L["roles"].get(t["role"], ""),
        "summary": t["summary"],
        "best-for": t["bestFor"],
        "strengths": ul(t["strengths"]),
        "limits": ul(t["limits"]),
        "questions": ul(t["questions"]),
        "business-models": ", ".join(L["models"].get(m, m) for m in t["models"]),
        "vendor-claim": (t.get("source") or {}).get("claim", ""),
        "source-url": (t.get("source") or {}).get("url", ""),
        "connected-applications": "".join(apps),
        "meta-title": meta_title(t["name"], " for personalization: strengths and limits | Speero"),
        "meta-description": clip(t["summary"], 155),
        "page-url": f"{TOOL_BASE}{t['id']}",
        "sort-order": order,
    }
    if logo_url:
        f["logo"] = {"url": logo_url, "alt": f"{t['name']} logo"}
    f["content-hash"] = content_hash(f)
    return f


def opp_fields(o, data, order, tool_item_ids):
    L = labels(data)
    opps = {x["id"]: x for x in data["opportunities"]}
    arms = data["taxonomy"]["arms"]

    signals = "".join(f"<h3>{e(L['signals'].get(s['kind'], s['kind']))}</h3><p>{e(s['example'])}</p>" for s in o["signals"])
    signals += f"<h3>Example eligibility rule</h3><p>{e(o['eligibilityRule'])}</p>"

    need = f"<p>{e(o['whatsGoingOn'])}</p><h3>Avoid this assumption</h3><p>{e(o['confusion'])}</p>"

    worth = (f"<p>{e(o['whyItEarns'])}</p>"
             "<h3>Reach</h3><p>How many eligible people can you reach in the chosen channel and time period?</p>"
             "<h3>Cost</h3><p>What will content, delivery, QA and ongoing maintenance cost?</p>"
             "<h3>Return</h3><p>What incremental outcome would cover that cost, and what is it worth?</p>"
             "<p><em>Planning inputs, not measured results. Estimate reach × incremental outcome rate × value per outcome, "
             "then subtract cost. Use a range and a consistent time period.</em></p>")

    fmt = o.get("format")
    response = (f"<p><strong>Example format: {e(fmt)}</strong></p>" if fmt else "") + f"<p>{e(o['arms']['medium'])}</p>"
    response += "<h3>Compare lighter and deeper responses</h3><p>Choose the lightest response that solves the need.</p>"
    response += "".join(f"<h4>{e(a['label'])}: {e(a['note'])}</h4><p>{e(o['arms'][a['key']])}</p>" for a in arms)
    response += "<h3>What to watch out for</h3>" + ul(o["pitfalls"])

    t = o["test"]
    moment = (f"<h3>Control</h3><p>{e(t['control'])}</p><h3>Treatment</h3><p>{e(t['treatment'])}</p>"
              f"<h3>Success measure</h3><p>{e(t['primaryMetric'])}</p><h3>Guardrail</h3><p>{e(t['guardrail'])}</p>")
    if t.get("audienceReadout"):
        moment += f"<p>{e(t['audienceReadout'])}</p>"
    moment += "<p><strong>Win or lose,</strong> record what worked, for whom and why. What you learn becomes the next signal.</p>"

    # The template shows this rather than a Collection List on the Tools
    # reference: a list filtered to the current item's references cannot be
    # set up or verified through the API, and an unfiltered one would show
    # every tool on every page.
    tools = {t["id"]: t for t in data["tools"]}
    tools_list = ("<ul>" + "".join(
        f'<li><a href="{attr(TOOL_BASE + i)}">{e(tools[i]["name"])}</a> {e(tools[i]["summary"])}</li>'
        for i in o["toolIds"] if i in tools) + "</ul>") if o["toolIds"] else ""

    related = "".join(
        f'<p><a href="{attr(OPP_BASE + r)}">{e(opps[r]["title"])}</a> {e(opps[r]["summary"])}</p>'
        for r in o["related"][:3] if r in opps)

    stage, need_l = L["stages"].get(o["stage"], ""), L["needs"].get(o["situation"], "")
    f = {
        "name": o["title"],
        "slug": o["id"],
        "summary": o["summary"],
        "customer-need": need_l,
        "journey-stage": stage,
        "business-models": ", ".join(L["models"].get(m, m) for m in o["models"]),
        "signals": signals,
        "the-need": need,
        "worth-it": worth,
        "the-response": response,
        "the-moment": moment,
        "related-situations": related,
        "tools-list": tools_list,
        "tools": [tool_item_ids[i] for i in o["toolIds"] if i in tool_item_ids],
        "meta-title": meta_title(o["title"].rstrip("."), " | Personalization use case | Speero"),
        "meta-description": clip(f"{o['summary']} {o['whatsGoingOn']}", 155),
        "page-url": f"{OPP_BASE}{o['id']}",
        "sort-order": order,
    }
    f["content-hash"] = content_hash({k: v for k, v in f.items() if k != "tools"} | {"tools": o["toolIds"]})
    return f


def hub_jsonld(data):
    """WebSite + Organization + CollectionPage with ItemLists of every
    opportunity and tool, for the /personalization-hub landing page."""
    def items(rows, base, name_key):
        return [{"@type": "ListItem", "position": i + 1, "url": SITE + base + r["id"], "name": r[name_key]}
                for i, r in enumerate(rows)]
    return {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "@id": SITE + "/#organization", "name": "Speero", "url": SITE},
            {"@type": "WebSite", "@id": SITE + "/#website", "url": SITE, "name": "Speero", "publisher": {"@id": SITE + "/#organization"}},
            {"@type": "CollectionPage", "@id": SITE + HUB, "url": SITE + HUB,
             "name": "Personalization Hub",
             "description": "A practical place to find where a different customer experience would help, check that it deserves to ship, and choose the tools that can deliver it.",
             "isPartOf": {"@id": SITE + "/#website"}, "publisher": {"@id": SITE + "/#organization"},
             "hasPart": [
                 {"@type": "ItemList", "name": "Personalization opportunities", "numberOfItems": len(data["opportunities"]),
                  "itemListElement": items(data["opportunities"], OPP_BASE, "title")},
                 {"@type": "ItemList", "name": "Personalization tools", "numberOfItems": len(data["tools"]),
                  "itemListElement": items(data["tools"], TOOL_BASE, "name")},
             ]},
        ],
    }
