# Speero Personalization Hub: Data

TL;DR: Airtable (Nick's base `appulGzKcE8TQIO70`) is meant to be the source of truth. A nightly GitHub Action builds `personalization-hub.json` for the embed and reconciles two Webflow CMS collections, so every opportunity and tool gets an indexable page. Until the Airtable field mapping is confirmed, the build runs from the prototype dataset and says so in the log.

```
https://cdn.jsdelivr.net/gh/speerotools/personalization-hub-data@main/personalization-hub.json
```

## The loop

`sync.yml` runs daily at 05:15 UTC and on demand:

1. `sync.py` reads Airtable and writes `personalization-hub.json`. While `AIRTABLE_MAPPED` is not `true` it runs `build.py` on `source/prototype-extract.json` instead.
2. `build.py` checks every reference (tools, stages, needs, related situations, library entries) and fails the run on a broken one.
3. The JSON is committed, so every change to live data has a diff.
4. `webflow_sync.py` reconciles the CMS collections, refreshes the landing page JSON-LD and purges the CDN.

## Scripts

| Script | What it does |
|---|---|
| `sync.py` | Airtable to JSON. `--schema` prints the base's tables and fields, the first step of finishing the mapping |
| `build.py` | Prototype extract to JSON, with referential checks |
| `extract_prototype.py` | One-off: parses the data literals out of the deployed prototype bundle without executing it |
| `render.py` | Pure functions: JSON to CMS field data and landing page JSON-LD |
| `webflow_sync.py` | Reconciles both collections, matched on `airtable-id` then slug |

## Webflow

Site `5fbb892601063dd93dd166d7`.

| What | Id | URL |
|---|---|---|
| Personalization Tools collection | `6ae871c2e332aa28943ce453` | `/personalization-tools/<slug>` |
| Personalization Opportunities collection | `6ae871c32b8db33bd1a3cf84` | `/personalization-opportunities/<slug>` |
| Landing page (draft) | `6ae872418849eb32398047d1` | `/personalization-hub` |

Opportunity fields follow the five steps: `signals`, `the-need`, `worth-it`, `the-response`, `the-moment`, plus `related-situations` and a `tools` multi-reference. Tool fields: `stack-role`, `summary`, `best-for`, `strengths`, `limits`, `questions`, `business-models`, `vendor-claim`, `source-url`, `logo`, `connected-applications`. Both carry `meta-title`, `meta-description`, `page-url`, `sort-order`, `last-modified`, `airtable-id`, `content-hash`, the same conventions as the Research Recipes collection.

The rich text fields carry their own H3s, so the template only binds one field per section under a static H2 (the step question).

## Secrets and variables

| Kind | Name | Value |
|---|---|---|
| Secret | `WEBFLOW_TOKEN` | Site token with CMS read/write, pages and publish. The research hub's token works |
| Secret | `AIRTABLE_TOKEN` | PAT with `data.records:read` + `schema.bases:read` on `appulGzKcE8TQIO70` |
| Variable | `AIRTABLE_MAPPED` | `true` once `read_airtable()` is implemented |
| Variable | `WEBFLOW_PUBLISH` | `true` publishes the CMS items each run changed. Leave off until the templates are designed |
| Variable | `WEBFLOW_SITE_PUBLISH` | `true` also publishes the whole site, including unfinished Designer work |
| Variable | `WEBFLOW_CUSTOM_DOMAINS` | Required with site publish, same ids as the research hub |

## Still open

- Airtable mapping: confirm the base's tables against the prototype data, then implement `read_airtable()`. Ben's research base (`appjlkXjUCGUTRHBi`) is separate; any merge is a decision, not a default.
- Designer work: landing page native H1, intro and Collection List directories, plus both CMS template pages, need the Webflow Designer open with the MCP app.
- Then switch the embed's `opportunityBase` and `toolBase` on, and turn `WEBFLOW_PUBLISH` on.

## Safety rails

Fewer than 10 tools or opportunities reads as a failed sync. Removals archive and are capped by `MAX_ARCHIVE`. Slug changes abort unless `allow_slug_change` is set after adding the 301. Site publish is opt-in.
