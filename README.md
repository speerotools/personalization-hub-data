# Speero Personalization Hub: Data

TL;DR: Airtable (Nick's base `appulGzKcE8TQIO70`) is the source of truth. A nightly GitHub Action builds `personalization-hub.json` for the embed and reconciles two Webflow CMS collections, so every opportunity and tool gets an indexable page. The Airtable reader is written; until the `AIRTABLE_MAPPED` variable is `true`, each run logs how Airtable differs from the prototype dataset and keeps publishing the prototype dataset.

```
https://cdn.jsdelivr.net/gh/speerotools/personalization-hub-data@main/personalization-hub.json
```

## The loop

`sync.yml` runs daily at 05:15 UTC and on demand:

1. `sync.py` reads Airtable and writes `personalization-hub.json`. While `AIRTABLE_MAPPED` is not `true` it logs the Airtable comparison and writes the prototype dataset instead.
2. `build.validate()` checks every reference (tools, stages, needs, signals, related situations, library entries, slugs) and fails the run on a broken one, whichever source the data came from.
3. The JSON is committed, so every change to live data has a diff.
4. `webflow_sync.py` reconciles the CMS collections, refreshes the landing page JSON-LD and purges the CDN.

## Scripts

| Script | What it does |
|---|---|
| `sync.py` | Airtable to JSON. `--check` reads and compares without writing; `--schema` records the base's structure in `airtable-schema.json` |
| `build.py` | Prototype extract to JSON; holds the shared `validate()` and `write()` |
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

## Airtable mapping

The table map is in the `sync.py` docstring. Select values (Situation, Stage, Contexts, Intents, Business Models) resolve through the Taxonomy table's `Select Option`, `Label` or `Slug`. Signals are one per line, written `Connected: Completed orders, ...`. Pitfalls, strengths, limits and questions are one per line; bullets are stripped. Records whose `Status` reads legacy, archived, inactive, retired, draft, hidden or deprecated are skipped.

Not read yet: Plays, Audit Groups (the earlier audit), the per-opportunity Reach, Cost and Return prompts (the embed shows the prototype's fixed prompts), Learning Loop, Website URL, and the per-business-model question examples.

Going live: run the workflow, read the "Airtable vs prototype" section of the log, and when the differences are the edits you expect, set `AIRTABLE_MAPPED` to `true`. A run with mapping problems writes nothing.

## Still open

- Ben's research base (`appjlkXjUCGUTRHBi`) is separate; any merge is a decision, not a default.
- Designer work: landing page native H1, intro and Collection List directories, plus both CMS template pages, need the Webflow Designer open with the MCP app.
- Then switch the embed's `opportunityBase` and `toolBase` on, and turn `WEBFLOW_PUBLISH` on.

## Safety rails

Fewer than 10 tools or opportunities reads as a failed sync. Removals archive and are capped by `MAX_ARCHIVE`. Slug changes abort unless `allow_slug_change` is set after adding the 301. Site publish is opt-in.
