# The Mamdani File

A deep-dive tracker of NYC Mayor Zohran Mamdani and the Democratic Socialists
of America. Third sibling of **Jew-hatred Today** and **American Law & Policy
— the Wire**: same engine, different product. The wires publish ranked
headline *links*; this publishes dated *entries* — each development pieced
together from multiple sources, with a written summary, a verbatim pulled
quote when one exists, and every source linked. It replaces the search-engine
digging it currently takes to assemble his day. Runs on your Mac every 4 hours.

## What it does

1. **Gathers** recent candidates — headlines *and their snippets* — from Bing
   News RSS (~50 targeted queries), NYC press-corps feeds (THE CITY, Gothamist,
   NY Post Metro, amNY, City & State, NYC Council press, The Hill), research
   outlets on a wider 3-week window (City Journal, Empire Center, Jacobin), and
   **primary sources**: his X accounts, his Bluesky, and the DSA's own organs
   (DSA National, Democratic Left, The Call). No API key needed for this step.
   (The mayor's office publishes no RSS; its press releases arrive via the
   "Mamdani announces" queries and the coverage they generate.)
2. **Tracks his social media directly.** X publishes no free feed, so both of
   his verified accounts — **@ZohranKMamdani** (personal) and **@NYCMayor**
   (official) — are pulled through Nitter mirror RSS (nitter.net first, then
   xcancel and tiekoetter), with X's own syndication/widget endpoint parsed as
   a last resort. Links are rewritten to the real `x.com` post; retweets are
   tagged "RT by" so the curator knows it's an amplification. Every route
   fails silently — if all mirrors are down, his posts still arrive via news
   coverage. Bluesky (`bsky.app/.../rss`) is also wired, though the account
   currently sits empty.
3. **Curates** with Claude (Opus 5) into deep-dive **entries** across six
   sections, plus one 🚨 SIREN and a 📅 **UPCOMING board** — concrete
   scheduled future happenings (hearings, votes, rallies, ceremonies, visits,
   court dates, conventions) extracted from the same fetched material, each
   dated as stated in the source and linked to it:
   - **In His Own Words** — statements, pressers, interviews, speeches, his
     social posts. Quotes are the point.
   - **Official Actions & Agenda** — executive orders, appointments, signings,
     vetoes, budgets, agency directives, program rollouts.
   - **Political & Unofficial Moves** — rallies, endorsements, meetings,
     fundraising, Hochul/Albany politics, intra-left maneuvering.
   - **Research, Reports & Deep Dives** — white papers, think-tank reports,
     studies, long-form investigations and profiles: background, affiliations,
     ideology, record. Wider recency window than the news beats.
   - **DSA Watch** — the org and movement: national + NYC-DSA, conventions,
     resolutions, endorsements, other candidates and electeds, membership,
     internal politics.
   - **Reaction & Fallout** — Hochul, Trump/Washington, business, labor, civic
     and Jewish-community responses, polls.
4. **Each entry** merges every outlet covering the same development into ONE
   item (primary source first, up to 3 more as a "MORE:" row), with a 1-3
   sentence dek written **only from the fetched headline/snippet material**,
   and an optional pulled quote.
5. **Anti-fabrication guarantees, in code:** Claude returns candidate
   *indices*, never re-typed URLs — every link is a real fetched URL. And
   every quote is machine-checked against the fetched text; anything not found
   verbatim is silently dropped before it renders.
6. **Scope boundary with the siblings:** this is a *subject* tracker —
   anything genuinely about Mamdani or the DSA is in scope here, **including**
   his Israel positions and Jewish-community flashpoints. General
   antisemitic-incident coverage with no Mamdani/DSA connection stays on
   jewhatredtoday.com; general law/courts/politics stays on amlawpolicy.com.
   (amlawpolicy.com keeps its own thin Mamdani/DSA headline sections; this is
   the deep version.)
7. **Prioritizes Gerard Filitti** — the dedicated `"Gerard Filitti"` search
   flags every article he appears in (including ones that only *quote* him).
   On-subject ones float to the top of their section (they do not hijack the
   siren; set `PRIORITY_AS_SIREN`-style behavior by editing `apply_priority`).
8. **Keeps a permanent Archive** so the main page stays a clean current
   edition while nothing is lost. Every run folds its entries into
   `public/archive.json` (near-duplicates within 7 days collapse into one
   story, sources unioned) and renders a date-grouped **archive.html**
   subpage — sirens flagged 🚨, section chips on every item, last 90 days
   shown with the full record retained in the JSON. The main page's masthead
   links to it ("THE ARCHIVE »") and it links back. The store is loaded from
   the local file *and* the live published copy and unioned, so Mac runs and
   GitHub Actions runs converge on one archive.
9. **Writes six files** into `public/`:
   - Sectioned: `index_sections.html` (preview) + `embed_sections.html` (paste). ← default
   - Flat ranked: `index.html` (preview) + `embed.html` (paste).
   - Archive: `archive.html` (subpage) + `embed_archive.html` (paste), plus
     the `archive.json` store.

If Claude declines a run, the request auto-retries on Anthropic's recommended
fallback model server-side (`fallbacks="default"`); if the API is entirely
unreachable, a keyword-only ranker still builds a headlines-only page.

---

## One-time setup

```bash
cd /Users/filitti/Downloads/mamdani-dsa-tracker
./setup_local.sh                       # creates venv, installs deps
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env    # your key from console.anthropic.com
./run.sh                               # test run -> writes public/*.html
open public/index_sections.html        # preview it
```

### Schedule it every 4 hours (launchd)

```bash
cp com.mamdanidsa.update.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mamdanidsa.update.plist
```

It runs immediately, then every 4 hours while you're logged in. Logs go to
`run.log`. To stop:
`launchctl unload ~/Library/LaunchAgents/com.mamdanidsa.update.plist`.

---

## Publishing

**Manual paste:** `./copy.sh` (sectioned) or `./copy.sh flat`, then paste into
a Code Block on your site and Save.

**Hands-off (self-updating):** create a GitHub repo (suggested name
`mamdani-dsa-tracker` under `gfilitti-ai`, matching the siblings), push, add
your `ANTHROPIC_API_KEY` as an Actions secret, enable Pages (Source: GitHub
Actions). The included workflow rebuilds ~every 4 hours with an hourly
freshness probe, exactly like amlawpolicy. Then paste `mamdanidsa-embed.html`
into your site once — it fetches the latest fragment client-side every 10
minutes.

```bash
cd /Users/filitti/Downloads/mamdani-dsa-tracker
git init -b main && git add -A && git commit -m "The Mamdani File: deep-dive Mamdani/DSA tracker"
gh repo create gfilitti-ai/mamdani-dsa-tracker --public --source . --push
gh secret set ANTHROPIC_API_KEY
```

---

## Tuning

- **Sources / topics:** `QUERIES` (Bing searches, grouped by section) and
  `DIRECT_FEEDS` (feeds; each entry sets label, broad/primary, and an optional
  per-feed age window).
- **Sections & scope:** the `SYSTEM` prompt (section definitions, merge rules,
  quote discipline) and the `SECTIONS` list (labels + order).
- **Recency:** `MAX_AGE_DAYS` (news, default 5), `RESEARCH_MAX_AGE_DAYS`
  (default 21), `PRIORITY_MAX_AGE_DAYS` (12).
- **Relevance gate for broad feeds:** `RELEVANCE_KW` — includes NYC-governance
  terms without his name ("City Hall", "rent freeze", "police commissioner"),
  because his administration's actions are the beat even when a headline
  doesn't say "Mamdani".
- **Priority names:** `PRIORITY_NAMES` / `PRIORITY_QUERIES`.
- **Refresh cadence:** `StartInterval` in the `.plist` (14400 = 4 hours).
- **Look:** the `_entry_block()` / `_content_sections()` renderers — only
  `<font>`/`<table>`/`<hr>`, no CSS, no JS, so it pastes cleanly anywhere.

## Files

- `generate.py` — the pipeline (gather → curate → verify quotes → render).
- `run.sh` / `setup_local.sh` / `copy.sh` — runner, setup, clipboard helper.
- `com.mamdanidsa.update.plist` — the 4-hour launchd schedule.
- `.env` — your `ANTHROPIC_API_KEY` (git-ignored).
- `public/index_sections.html`, `public/embed_sections.html` — sectioned (default).
- `public/index.html`, `public/embed.html` — flat ranked layout.
- `public/archive.html`, `public/embed_archive.html`, `public/archive.json` — the archive.
- `mamdanidsa-embed.html` — client-side self-updating snippet for the hosted version.
- `.github/workflows/update.yml` — the cloud alternative (Actions + Pages).

## Notes / limitations

- Direct feeds give clean publisher links; Bing items are redirect URLs that
  resolve to the publisher in a browser.
- Deks are grounded in headlines + RSS snippets, not full article text — they
  summarize what the sources published, and the links carry the depth.
- X posts arrive via Nitter mirrors, which flake from time to time; the
  pipeline tries three mirrors then X's own widget endpoint, and if all fail
  that run simply carries no direct posts (coverage still catches the big
  ones). Tune `X_ACCOUNTS` / `X_MIRRORS` in `generate.py`.
- Archive knobs: `ARCHIVE_RENDER_DAYS` (90), `ARCHIVE_DEDUPE_DAYS` (7),
  `ARCHIVE_REMOTE` (the live JSON URL — update if the repo name differs), and
  `ARCHIVE_PUBLIC_URL` (the absolute archive link used inside pasted embeds).
- socialists.nyc (NYC-DSA) has feeds disabled and cbcny.org blocks robots;
  their output arrives via the Bing queries instead.
