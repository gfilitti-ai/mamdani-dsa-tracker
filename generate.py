#!/usr/bin/env python3
"""
The Mamdani File — a deep-dive tracker of Zohran Mamdani and the Democratic
Socialists of America. Third sibling of Jew-hatred Today and American Law &
Policy: same gather->curate->render engine, but a different product. Where the
wires publish ranked headline LINKS, this tracker publishes dated ENTRIES —
each one a development pieced together from multiple sources, with a written
summary (dek), a verbatim pulled quote when one exists, and every source
linked. The point is to replace the search-engine digging it currently takes
to assemble his day: what he said, what he did, what's being written about
him, and what the DSA is doing.

Sections:
  1. IN HIS OWN WORDS            — statements, quotes, pressers, interviews,
     speeches, and his own social posts (Bluesky feed is pulled directly).
  2. OFFICIAL ACTIONS & AGENDA   — executive orders, appointments, signings,
     vetoes, budgets, agency directives, policy rollouts, administration moves.
  3. POLITICAL & UNOFFICIAL MOVES — rallies, endorsements, meetings, travel,
     fundraising, campaign-style activity, intra-party maneuvering.
  4. RESEARCH, REPORTS & DEEP DIVES — white papers, think-tank reports,
     studies, long-form investigations and profiles: his background,
     affiliations, ideology, record. Wider recency window than the news beats.
  5. DSA WATCH                   — the org and movement: national + chapters,
     conventions, resolutions, endorsements, candidates and electeds (other
     than Mamdani), membership, internal politics, publications.
  6. REACTION & FALLOUT          — responses to him: Hochul, Trump and
     Washington, business, labor, civic and Jewish communities, polling,
     editorials tied to a real development.

Boundary with the sibling sites (documented, not enforced in code):
  This is a SUBJECT tracker — anything genuinely about Mamdani or the DSA is
  in scope here, including his Israel positions and Jewish-community
  flashpoints. General antisemitic-incident coverage with no Mamdani/DSA
  connection stays on jewhatredtoday.com; general law/courts/politics with no
  Mamdani/DSA connection stays on amlawpolicy.com.

Pipeline:
  1. Gather candidates from Bing News RSS (topical queries), direct beat
     feeds, and primary sources (his Bluesky account, DSA org feeds). Keep
     each candidate's SNIPPET, not just its headline — the deks are written
     from that material.
  2. Deduplicate and hard-gate on true publish dates in code.
  3. Curate with Claude (Opus 5): merge same-event coverage into single
     entries (up to 4 source indices each), tag a section, write the headline
     and a 1-3 sentence dek grounded ONLY in the provided material, pull a
     verbatim quote when one appears, rank, pick one SIREN. The model returns
     candidate INDICES, never re-typed URLs, so every link is a real fetched
     URL — and every quote is verified in code against the fetched text
     before it renders; anything not found verbatim is dropped.
  4. Render Drudge-flavored, <font>-tagged, no-CSS/no-JS HTML in four files
     (sectioned + flat, each as full page + paste-ready fragment).

No API key present? Falls back to a keyword-only ranker (headlines only, no
deks) so the page still builds.
"""

import calendar
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

import feedparser

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "public/index.html")
MODEL = "claude-opus-5"
# Bing reports each article's TRUE publish date (unlike Google News, which
# re-dates resurfaced stories), so the hard age gate below actually works.
BING_FRESHNESS = "7"          # Bing qft "interval" value (~last week)
MAX_CANDIDATES = 320          # cap sent to the model, to bound token cost

# Hard age ceilings, enforced in code on each item's true publish date.
MAX_AGE_DAYS = 5              # news beats: statements, actions, reaction
RESEARCH_MAX_AGE_DAYS = 21    # think-tank reports / long-form stay relevant
PRIORITY_MAX_AGE_DAYS = 12    # priority (Filitti) coverage may be older
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Names to always surface when their coverage is on-subject. Matched on
# headline substring; the dedicated PRIORITY_QUERIES search also catches
# pieces that only QUOTE the person. Unlike the wires, priority stories float
# to the top of their section but do NOT hijack the siren — the siren is
# reserved for the biggest Mamdani/DSA development of the moment.
PRIORITY_NAMES = ["gerard filitti", "filitti"]
PRIORITY_QUERIES = ["Gerard Filitti"]

# ---------------------------------------------------------------------------
# X / Twitter. X publishes no free feed, so his accounts are pulled through
# Nitter mirrors (plain RSS; tried in order until one yields posts) with X's
# own syndication/widget endpoint as a last-resort parser. All routes fail
# silently — when every mirror is down, his posts still arrive via news
# coverage. Links are rewritten to x.com so readers land on the real post.
# ---------------------------------------------------------------------------
X_ACCOUNTS = [
    ("ZohranKMamdani", "X @ZohranKMamdani"),   # personal account
    ("NYCMayor",       "X @NYCMayor"),         # official mayoral account
]
X_MIRRORS = [
    "https://nitter.net/{}/rss",
    "https://xcancel.com/{}/rss",
    "https://nitter.tiekoetter.com/{}/rss",
]
X_MAX_PER_ACCOUNT = 12        # most-recent posts kept per account per run

# ---------------------------------------------------------------------------
# Archive. Every run merges its curated entries into public/archive.json and
# renders them as a date-grouped archive page, so the main page stays a clean
# current edition while nothing is lost. The store is loaded from the local
# file AND (best-effort) from the live published copy, then unioned — so Mac
# runs and GitHub Actions runs converge on one archive even though Actions
# starts from a fresh checkout.
# ---------------------------------------------------------------------------
ARCHIVE_PATH = os.environ.get("ARCHIVE_PATH", "public/archive.json")
ARCHIVE_REMOTE = os.environ.get(
    "ARCHIVE_REMOTE",
    "https://gfilitti-ai.github.io/mamdani-dsa-tracker/archive.json")
ARCHIVE_RENDER_DAYS = 90      # days shown on archive.html (JSON keeps all)
ARCHIVE_DEDUPE_DAYS = 7       # same-headline window treated as one story
# Absolute URLs used for cross-links inside pasted embed fragments (relative
# links would break on the embedding site's domain). These point at the
# Squarespace pages that HOST the embeds, so readers never leave the site.
MAIN_PUBLIC_URL = "https://www.amlawpolicy.com/mamdani"
ARCHIVE_PUBLIC_URL = "https://www.amlawpolicy.com/mamdani-archive"

# ---------------------------------------------------------------------------
# Sections. The curator tags every entry with one; the sectioned layout groups
# by these, in this order. Keep the enum values in sync with SCHEMA below.
# ---------------------------------------------------------------------------
SECTIONS = [
    ("Words",     "IN HIS OWN WORDS"),
    ("Official",  "OFFICIAL ACTIONS &amp; AGENDA"),
    ("Political", "POLITICAL &amp; UNOFFICIAL MOVES"),
    ("Research",  "RESEARCH, REPORTS &amp; DEEP DIVES"),
    ("DSA",       "DSA WATCH"),
    ("Reaction",  "REACTION &amp; FALLOUT"),
]
SECTION_ORDER = [k for k, _ in SECTIONS]
SECTION_LABELS = dict(SECTIONS)
DEFAULT_SECTION = "Reaction"

# Topical Bing News searches. Broad on purpose — Claude does the fine
# filtering and section routing. Grouped by the section they mostly feed.
QUERIES = [
    # --- In His Own Words: statements, quotes, media, social ---
    "Zohran Mamdani",
    "Mayor Mamdani",
    "Mamdani said",
    "Mamdani statement",
    "Mamdani speech OR remarks",
    "Mamdani interview",
    "Mamdani press conference",
    "Mamdani posted OR tweeted",
    # --- Official actions & agenda ---
    "Mamdani announces",
    "Mamdani executive order OR directive",
    "Mamdani appoints OR names OR taps",
    "Mamdani signs OR vetoes",
    "Mamdani budget",
    "Mamdani administration",
    "Mamdani City Hall",
    "Mamdani NYPD OR public safety",
    "Mamdani Department of Community Safety",
    "Mamdani rent freeze OR rent guidelines",
    "Mamdani free buses OR MTA",
    "Mamdani grocery stores",
    "Mamdani childcare",
    "Mamdani housing",
    "Mamdani schools OR education",
    "Mamdani immigration OR ICE",
    # --- Political & unofficial moves ---
    "Mamdani rally",
    "Mamdani endorses OR endorsement",
    "Mamdani campaign OR fundraising",
    "Mamdani Hochul",
    "Mamdani Albany",
    "Mamdani Democratic Party",
    "Mamdani union OR labor",
    # --- Research, reports & deep dives ---
    "Mamdani report OR study",
    "Mamdani white paper OR analysis",
    "Mamdani profile OR investigation",
    "Mamdani ideology OR socialism",
    "Mamdani record OR background",
    "Mamdani affiliations OR ties",
    # --- DSA Watch ---
    "Democratic Socialists of America",
    "NYC-DSA OR \"New York City Democratic Socialists\"",
    "DSA endorsement OR candidate",
    "DSA convention OR resolution",
    "DSA membership",
    "DSA chapter",
    "democratic socialist primary OR elected",
    "Claire Valdez OR Avila Chevalier",
    # --- Reaction & fallout ---
    "Mamdani Trump",
    "Mamdani White House OR federal government",
    "Mamdani poll OR approval rating",
    "Mamdani Wall Street OR business leaders",
    "Mamdani Jewish community OR Israel",
    "Mamdani criticism OR backlash",
    "Mamdani lawsuit",
]

# Research-flavored queries get the wider age window (matched by list slice
# below rather than duplicating the strings).
RESEARCH_QUERIES = {
    "Mamdani report OR study",
    "Mamdani white paper OR analysis",
    "Mamdani profile OR investigation",
    "Mamdani ideology OR socialism",
    "Mamdani record OR background",
    "Mamdani affiliations OR ties",
}

# Direct feeds: (url, label, broad, max_age_days_or_None).
#   broad=True  -> general outlet; items must pass RELEVANCE_KW.
#   broad=False -> primary/topical source; everything recent passes.
# All verified live 2026-07 (nyc.gov's mayor's office publishes no RSS — its
# press releases arrive via the Bing "Mamdani announces" queries and coverage).
DIRECT_FEEDS = [
    # Primary sources
    ("https://bsky.app/profile/zohrankmamdani.bsky.social/rss",
     "Bluesky @zohrankmamdani", False, None),          # his own posts
    ("https://www.dsausa.org/feed/", "DSA National", False, None),
    ("https://democraticleft.dsausa.org/feed/", "Democratic Left", False, None),
    ("https://socialistcall.com/feed/", "The Call (DSA)", False, None),
    # NYC press corps (broad: relevance-filtered)
    ("https://www.thecity.nyc/feed/", "THE CITY", True, None),
    ("https://gothamist.com/feed", "Gothamist", True, None),
    ("https://nypost.com/metro/feed/", "NY Post Metro", True, None),
    ("https://www.amny.com/feed/", "amNY", True, None),
    ("https://www.cityandstateny.com/rss/all", "City & State NY", True, None),
    ("https://council.nyc.gov/press/feed/", "NYC Council Press", True, None),
    # National politics (broad)
    ("https://thehill.com/homenews/feed/", "The Hill", True, None),
    # Research / long-form (broad, wider window)
    ("https://www.city-journal.org/rss.xml", "City Journal", True, RESEARCH_MAX_AGE_DAYS),
    ("https://www.empirecenter.org/feed/", "Empire Center", True, RESEARCH_MAX_AGE_DAYS),
    ("https://jacobin.com/feed", "Jacobin", True, RESEARCH_MAX_AGE_DAYS),
]

# An item from a broad DIRECT_FEED is kept only if headline or snippet matches
# one of these. NYC-governance terms are included without his name because his
# administration's actions are the beat even when a headline says "City Hall".
RELEVANCE_KW = [
    "mamdani", "zohran",
    " dsa ", " dsa'", " dsa-", "dsa:", "nyc-dsa",
    "democratic socialist", "socialists of america", "socialist",
    "city hall", "mayor's office", "mayor of new york", "nyc mayor",
    "new york city mayor", "the mayor", "gracie mansion",
    "first deputy mayor", "police commissioner", "nypd commissioner",
    "schools chancellor", "city budget", "rent guidelines board",
    "rent freeze", "fare-free", "free buses", "city-owned grocery",
    "department of community safety", "economic development corporation",
]

# Hard exclusions. Deliberately empty: this is a subject-scoped tracker, and
# the subject boundary is handled by the queries, the relevance filter, and
# the curator. (The sibling sites' antisemitism-incident beat is excluded by
# instruction in the SYSTEM prompt, not by keyword, because Mamdani-related
# Israel/Jewish-community stories ARE in scope here.)
EXCLUDE_KW = []

SYSTEM = """\
You are the editor of "The Mamdani File", a deep-dive tracker of New York City \
Mayor Zohran Mamdani and the Democratic Socialists of America. Readers use it \
instead of digging through search engines: it must capture what he is SAYING, \
what he is DOING (officially and unofficially), what is being WRITTEN about \
him, and what the DSA is doing — several times a day.

You are given a numbered list of recent candidates. Each has a headline, a \
source, an age, and usually a snippet. Some carry tags: [X-POST] items are \
posts pulled directly from Mamdani's own verified X accounts (@ZohranKMamdani \
personal; @NYCMayor official) and [BLUESKY] from his verified Bluesky — both \
are PRIMARY sources; a title beginning "RT by" is a repost he amplified, \
worth including only when the amplification itself is telling. [FILITTI] \
items surfaced from a search for legal analyst Gerard Filitti, who may be \
quoted even when his name is not in the headline.

YOUR JOB: build ENTRIES, not a link list. An entry is one real-world \
development, assembled from every candidate that covers it.

FOR EACH ENTRY RETURN:
- "indices": 1-4 candidate indices covering this development. FIRST index = \
primary source (the clearest, most authoritative, or original outlet — prefer \
the primary document or the outlet that broke it). Additional indices are \
other outlets' coverage of the SAME development, so readers can triangulate. \
Never list two different developments in one entry.
- "section": exactly one of the sections defined below.
- "headline": your own tight, factual, specific headline for the development \
(name the action or claim; no clickbait, no editorializing).
- "dek": 1-3 sentences summarizing the development. Write it ONLY from the \
provided headlines and snippets of THIS entry's indices. Never import outside \
knowledge, never speculate, never state specifics (numbers, dates, names) that \
do not appear in the provided material. If the snippets are thin, keep the dek \
to one modest sentence.
- "quote": a short VERBATIM quote copied word-for-word from the provided \
headline/snippet text of this entry's indices — quotation is the heart of the \
"In His Own Words" beat. It must be a PERSON'S spoken or written words \
(Mamdani's above all, else the key actor's), normally text that sits inside \
quotation marks in the source material — never the outlet's own narration, \
headline prose, or subhead. If no usable speaker quote appears in the \
provided material, return "" — NEVER compose, paraphrase, or stitch a quote. \
(Quotes are machine-checked against the source text; an invented quote is \
discarded.)

THE SECTIONS:
- "Words"     = what Mamdani himself said: statements, press conferences, \
interviews, speeches, notable exchanges, and his own social posts. [X-POST] \
and [BLUESKY] items belong here (quote = the post text; the post itself is \
the primary source — and when news coverage and his own post describe the \
same development, MERGE them into one entry with his post as an index). A \
story whose core is "Mamdani said X" goes here even when X touches policy. \
Do not list more than ~3 routine social posts; prefer the consequential ones.
- "Official"  = official mayoral action and agenda: executive orders and \
directives, appointments and personnel, signings and vetoes, budget moves, \
agency actions, program launches and rollouts, administration filings and \
rules. The core is "the administration DID something".
- "Political" = unofficial and political action: rallies, endorsements he \
makes or receives, meetings, travel, fundraising, campaign-style activity, \
party and intra-left maneuvering, his dealings with Hochul and Albany when \
they are political rather than governmental.
- "Research"  = white papers, think-tank reports, studies, data analyses, \
long-form investigations and profiles examining Mamdani — his background, \
family, education, affiliations, ideology, funding, record, network. Items \
here may be up to ~3 weeks old; substance matters more than freshness. Pure \
op-eds belong here ONLY if they are substantial research/analysis, not mere \
opinion.
- "DSA"       = the Democratic Socialists of America as an organization and \
movement: national and chapters (especially NYC-DSA), conventions and \
resolutions, endorsements, candidates and elected members OTHER than Mamdani, \
membership, internal politics, its publications' significant output. If a \
story involves both Mamdani and the DSA, tag "DSA" only when the organization \
is the primary subject.
- "Reaction"  = responses TO Mamdani and fallout around him: Hochul, Trump \
and Washington, federal actions aimed at him or the city, business and Wall \
Street, labor, civic and Jewish-community responses, polling, notable \
editorial reaction tied to a concrete development.

SCOPE — INCLUDE: anything genuinely about Mamdani (including his Israel \
positions, Jewish-community flashpoints, personal controversies, family and \
biography coverage) or about the DSA. EXCLUDE: stories with no real \
Mamdani/DSA connection — generic NYC or national politics, other officials' \
unrelated business, and antisemitic-incident coverage unconnected to \
Mamdani/DSA (a sibling site covers that beat). Also exclude pure \
business/sports/celebrity items and thin hot-take opinion with no development.

GERARD FILITTI: include a [FILITTI] item only when it is on-subject \
(Mamdani/DSA-related); place it in its natural section and rank it FIRST \
within that section. Pick the single best version of the event. Ignore \
off-subject [FILITTI] items entirely.

DEDUPLICATE BY EVENT: many outlets cover the same development. That is what \
the multi-index entry is for — ONE entry per development, best source first, \
up to 3 more as corroboration. A development must appear at most once on the \
whole page.

RECENCY & CURRENCY: ages are shown. Prefer fresh developments; the test is \
the date of the DEVELOPMENT, not the article. Exclude recaps, anniversary \
pieces, and re-reports of old news (except genuine "Research" items, which \
may analyze older material). A new step in an older matter — a response \
filed, an appointment confirmed, a report released — is in scope.

UPCOMING EVENTS: separately from the entries, scan ALL candidate material \
for concrete FUTURE happenings that are actually scheduled or announced. \
ON-SUBJECT ONLY: an event belongs on this board only when Mamdani or the DSA \
is a participant, target, or central stake — his public schedule, \
appearances, and travel; hearings, votes, and deadlines on his agenda or \
aimed at him; rallies, marches, and protests about him; court dates \
involving him or his administration; DSA conventions, meetings, and \
elections featuring DSA candidates; visits and ceremonies where he is a \
flashpoint. EXCLUDE routine civic-calendar items — transit service changes, \
weather, street closures, generic city programming — even when a city \
agency announces them. \
NOT ALREADY PAST: you are told today's date; every event must still be ahead \
of it. Resolve relative dates against the ARTICLE'S age — "Monday" or \
"tomorrow" in a 3-day-old piece has usually already happened; if you cannot \
confidently place the event in the future, leave it out. Prefer events the \
material dates explicitly. \
Return them in "events": "when" is the date or timeframe as stated (e.g. \
"Aug 2", "Sept 11"); "what" is one grounded line naming the event; "indices" \
cites 1-2 candidates that mention it. Soonest first. 0-8 events; return [] \
rather than inventing, guessing, or padding.

VOLUME & RANKING: aim for roughly 4-8 entries per section when material \
supports it; skip a section rather than pad it. Within each section, rank \
most significant first. Choose the single most consequential development as \
the SIREN and give it a punchy factual headline (shown ALL CAPS) plus a \
one-sentence dek; do not repeat it as a regular entry.\
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "siren": {
            "type": "object",
            "properties": {
                "index": {"type": "integer",
                          "description": "Candidate index of the siren development's primary source."},
                "headline": {"type": "string",
                             "description": "Punchy, factual siren headline (shown ALL CAPS)."},
                "dek": {"type": "string",
                        "description": "One-sentence summary grounded in the provided material."},
                "section": {"type": "string", "enum": SECTION_ORDER},
            },
            "required": ["index", "headline", "dek", "section"],
            "additionalProperties": False,
        },
        "entries": {
            "type": "array",
            "description": "All other entries, ranked most significant first within the whole list.",
            "items": {
                "type": "object",
                "properties": {
                    "indices": {"type": "array", "items": {"type": "integer"},
                                "description": "1-4 candidate indices; primary source first."},
                    "section": {"type": "string", "enum": SECTION_ORDER},
                    "headline": {"type": "string"},
                    "dek": {"type": "string"},
                    "quote": {"type": "string",
                              "description": "Verbatim quote from the provided material, or \"\"."},
                },
                "required": ["indices", "section", "headline", "dek", "quote"],
                "additionalProperties": False,
            },
        },
        "events": {
            "type": "array",
            "description": "Concrete scheduled future happenings found in the material; [] if none.",
            "items": {
                "type": "object",
                "properties": {
                    "when": {"type": "string",
                             "description": "Date/timeframe as stated in the material."},
                    "what": {"type": "string",
                             "description": "One grounded line naming the event."},
                    "indices": {"type": "array", "items": {"type": "integer"},
                                "description": "1-2 candidate indices mentioning it."},
                },
                "required": ["when", "what", "indices"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["siren", "entries", "events"],
    "additionalProperties": False,
}

# Keywords for the no-API fallback ranker (crude include gate).
INCLUDE_KW = [
    "mamdani", "zohran", "democratic socialist", "socialists of america",
    " dsa ", "dsa:", "nyc-dsa", "socialist", "city hall", "nyc mayor",
    "new york city mayor", "rent freeze", "free buses", "city-owned grocery",
]


# ---------------------------------------------------------------------------
# Gather
# ---------------------------------------------------------------------------

def _fetch(url):
    return feedparser.parse(url, agent=UA)


def _clean_title(raw):
    """News-RSS titles often look like 'Headline - Publisher'. Split off the source."""
    raw = html.unescape(raw or "").strip()
    source = ""
    if " - " in raw:
        head, tail = raw.rsplit(" - ", 1)
        if 0 < len(tail) <= 40 and "http" not in tail:
            raw, source = head.strip(), tail.strip()
    return raw, source


_TAG_RE = re.compile(r"<[^>]+>")


def _clean_snippet(raw, limit=280):
    """Strip HTML, unescape, collapse whitespace, truncate at a word break."""
    if not raw:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", raw))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


def _norm(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _excluded(text):
    t = text.lower()
    return any(k in t for k in EXCLUDE_KW)


def _relevant(text):
    """Keep broad-outlet items only if headline or snippet is on-subject."""
    t = " " + text.lower() + " "
    return any(k in t for k in RELEVANCE_KW)


# Coarse section guess for the fallback path and for entries the model didn't
# tag. Precedence is deliberate: the specific lanes first, Reaction as default.
_SECTION_HINTS = [
    ("DSA", ["democratic socialists", "democratic socialist", " dsa ", " dsa'",
             "dsa endorse", "nyc-dsa", "socialists of america", "socialist caucus",
             "valdez", "avila chevalier"]),
    ("Research", ["report", "study", "white paper", "analysis", "profile",
                  "investigation", "the making of", "inside the", "how mamdani",
                  "who is", "explained"]),
    ("Official", ["announces", "appoint", "names", "taps", "signs", "vetoes",
                  "executive order", "directive", "budget", "launches",
                  "unveils", "orders", "rolls out", "administration", "agency",
                  "commissioner", "chancellor"]),
    ("Political", ["rally", "endorse", "campaign", "fundrais", "hochul",
                   "albany", "union", "primary", "party"]),
    ("Words", ["said", "says", "statement", "speech", "interview", "remarks",
               "vows", "pledges", "calls for", "defends", "responds", "tells",
               "asked about", "posted", "tweet"]),
    ("Reaction", ["trump", "white house", "federal", "poll", "approval",
                  "wall street", "business leaders", "reacts", "backlash",
                  "criticism", "warns", "blasts", "slams", "lawsuit"]),
]


def guess_section(candidate):
    src = candidate.get("source", "")
    if candidate.get("social") or src.startswith(("Bluesky", "X @")):
        return "Words"
    if src in ("DSA National", "Democratic Left", "The Call (DSA)"):
        return "DSA"
    text = (candidate["title"] + " " + candidate.get("snippet", "")).lower()
    for section, hints in _SECTION_HINTS:
        if any(h in text for h in hints):
            return section
    return DEFAULT_SECTION


_NITTER_HOST_RE = re.compile(r"https?://[^/]+/")


def _x_link(nitter_link, handle):
    """Rewrite a Nitter status link to the real x.com post."""
    m = re.search(r"/status/(\d+)", nitter_link or "")
    if m:
        return f"https://x.com/{handle}/status/{m.group(1)}"
    return _NITTER_HOST_RE.sub("https://x.com/", nitter_link or "", count=1)


def _x_candidates_from_feed(feed, handle, label, now):
    out = []
    for e in feed.entries[:X_MAX_PER_ACCOUNT * 2]:
        pub = getattr(e, "published_parsed", None)
        if pub is None or (now - calendar.timegm(pub)) > MAX_AGE_DAYS * 86400:
            continue
        text = html.unescape(getattr(e, "title", "") or "").strip()
        if not text:
            continue
        title = text if len(text) <= 200 else text[:200].rsplit(" ", 1)[0] + "…"
        out.append({
            "title": title,
            "source": label,
            "link": _x_link(getattr(e, "link", ""), handle),
            # Full post text (generous cap) so pulled quotes verify against
            # complete sentences instead of a truncation boundary.
            "snippet": _clean_snippet(text, limit=600) if len(text) > 200 else "",
            "published": pub,
            "priority": False,
            "social": True,
            "stag": "X-POST",
        })
        if len(out) >= X_MAX_PER_ACCOUNT:
            break
    return out


def _x_syndication(handle, label, now):
    """Last-resort: parse X's own widget endpoint (__NEXT_DATA__ JSON)."""
    import urllib.request
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        page = resp.read().decode("utf-8", "replace")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                  page, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    entries = (data.get("props", {}).get("pageProps", {})
                   .get("timeline", {}).get("entries", []))
    out = []
    for ent in entries:
        tw = (ent.get("content") or {}).get("tweet") or {}
        text = (tw.get("full_text") or "").strip()
        tid = tw.get("id_str") or ""
        created = tw.get("created_at") or ""
        if not text or not tid:
            continue
        try:
            dt = datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y")
            pub = dt.utctimetuple()
        except ValueError:
            continue
        if (now - calendar.timegm(pub)) > MAX_AGE_DAYS * 86400:
            continue
        title = text if len(text) <= 200 else text[:200].rsplit(" ", 1)[0] + "…"
        out.append({
            "title": title,
            "source": label,
            "link": f"https://x.com/{handle}/status/{tid}",
            "snippet": _clean_snippet(text, limit=600) if len(text) > 200 else "",
            "published": pub,
            "priority": False,
            "social": True,
            "stag": "X-POST",
        })
        if len(out) >= X_MAX_PER_ACCOUNT:
            break
    return out


def gather_x(now):
    """Fetch Mamdani's own X posts: Nitter mirrors first, syndication last.
    Every route tolerates failure — worst case his posts arrive via coverage."""
    candidates = []
    for handle, label in X_ACCOUNTS:
        got = []
        for mirror in X_MIRRORS:
            try:
                feed = _fetch(mirror.format(handle))
                got = _x_candidates_from_feed(feed, handle, label, now)
            except Exception:
                got = []
            if got:
                break
        if not got:
            try:
                got = _x_syndication(handle, label, now)
            except Exception:
                got = []
        candidates += got
    return candidates


def gather():
    seen_titles, seen_links = set(), set()
    candidates = []

    def bing_url(q):
        return ("https://www.bing.com/news/search?q="
                + urllib.parse.quote(q)
                + "&qft=interval%3d%22" + BING_FRESHNESS + "%22&format=rss&setmkt=en-US")

    # (url, label, is_priority, broad, max_age_override). Priority feeds first
    # so their flag wins on de-dupe.
    sources = [(bing_url('"' + q + '"'), "", True, False, None) for q in PRIORITY_QUERIES]
    sources += [(bing_url(q), "", False, False,
                 RESEARCH_MAX_AGE_DAYS if q in RESEARCH_QUERIES else None)
                for q in QUERIES]
    sources += [(url, label, False, broad, age) for url, label, broad, age in DIRECT_FEEDS]

    now = time.time()
    for url, label, is_priority, broad, age_override in sources:
        feed = _fetch(url)
        feed_title = (feed.feed.get("title") or "").strip()
        for e in feed.entries:
            link = getattr(e, "link", "").strip()
            title, source = _clean_title(getattr(e, "title", ""))
            if not link or not title:
                continue
            if not source:
                source = (getattr(e, "news_source", "") or "").strip()   # Bing publisher
            if not source:
                src = getattr(e, "source", None)
                source = getattr(src, "title", "") if src else ""
            if not source:
                source = label or feed_title
            snippet = _clean_snippet(getattr(e, "summary", "")
                                     or getattr(e, "description", ""))
            if snippet and _norm(snippet) == _norm(title):
                snippet = ""                     # snippet that just repeats the headline
            if _excluded(title + " " + snippet):
                continue
            # Broad outlet feeds carry off-topic content — keep on-subject only.
            if broad and not _relevant(title + " " + snippet):
                continue
            # Hard recency gate on the item's TRUE publish date. Undated items
            # are dropped, priority included — age can't be verified.
            pub = getattr(e, "published_parsed", None)
            if pub is None:
                continue
            max_age = (PRIORITY_MAX_AGE_DAYS if is_priority
                       else (age_override or MAX_AGE_DAYS))
            if (now - calendar.timegm(pub)) > max_age * 86400:
                continue
            key = _norm(title)
            if not key or key in seen_titles or link in seen_links:
                continue
            seen_titles.add(key)
            seen_links.add(link)
            is_bsky = label.startswith("Bluesky")
            candidates.append({
                "title": title,
                "source": source or "News",
                "link": link,
                "snippet": snippet,
                "published": pub,
                "priority": is_priority,
                "social": is_bsky,
                "stag": "BLUESKY" if is_bsky else "",
            })

    # His own X posts (Nitter mirrors -> syndication fallback), deduped in.
    for c in gather_x(now):
        key = _norm(c["title"])
        if not key or key in seen_titles or c["link"] in seen_links:
            continue
        seen_titles.add(key)
        seen_links.add(c["link"])
        candidates.append(c)

    # Most recent first; the cap never drops a priority or own-account item.
    candidates.sort(key=lambda c: c["published"] or (), reverse=True)
    capped = candidates[:MAX_CANDIDATES]
    extra = [c for c in candidates[MAX_CANDIDATES:]
             if c.get("priority") or c.get("social")]
    return capped + extra


# ---------------------------------------------------------------------------
# Curate
# ---------------------------------------------------------------------------

def _age_str(c, now):
    p = c.get("published")
    if not p:
        return "undated"
    days = (now - calendar.timegm(p)) / 86400
    return "today" if days < 1 else f"{days:.0f}d ago"


def _date_str(c):
    p = c.get("published")
    if not p:
        return ""
    return datetime.fromtimestamp(calendar.timegm(p), ZoneInfo("America/New_York")).strftime("%b %-d")


def _normalize_for_match(text):
    """Loosen quote matching: unify curly punctuation, case, whitespace."""
    text = unicodedata.normalize("NFKC", text or "")
    text = (text.replace("‘", "'").replace("’", "'")
                .replace("“", '"').replace("”", '"')
                .replace("–", "-").replace("—", "-")
                .replace("…", "..."))
    return re.sub(r"\s+", " ", text).strip().lower()


def _verify_quote(quote, cands):
    """Keep a quote only if it appears verbatim in the provided material."""
    q = _normalize_for_match(quote).strip("\"'.,; ")
    if len(q) < 8:
        return ""
    for c in cands:
        hay = _normalize_for_match(c["title"] + " " + c.get("snippet", ""))
        if q in hay:
            return quote.strip()
    return ""


def curate_llm(candidates):
    import anthropic

    client = anthropic.Anthropic()
    now = time.time()

    lines = []
    for i, c in enumerate(candidates):
        tags = ""
        if c.get("priority"):
            tags += "[FILITTI] "
        if c.get("stag"):
            tags += f"[{c['stag']}] "
        line = f"[{i}] {tags}{c['title']} ({c['source']}, {_age_str(c, now)})"
        if c.get("snippet"):
            line += f"\n     > {c['snippet']}"
        lines.append(line)
    listing = "\n".join(lines)

    today = datetime.now(ZoneInfo("America/New_York")).strftime("%A, %B %-d, %Y")
    user = (
        f"Today is {today} (America/New_York). "
        "Here are the candidates. Build the entries (merging same-event "
        "coverage, primary source first), write grounded deks and verbatim "
        "quotes, tag sections, rank, pick the siren, and extract only "
        "on-subject, genuinely future events.\n\n" + listing
    )

    # Server-side fallback: if Opus 5's safety classifiers decline a run,
    # the request is re-run on Anthropic's recommended fallback model in the
    # same call, so the page still gets a real curation instead of dropping
    # to the keyword ranker.
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=20000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        raise RuntimeError("Model declined the request (refusal).")

    text = next(b.text for b in msg.content if b.type == "text")
    data = json.loads(text)

    n = len(candidates)

    def ok(i):
        return isinstance(i, int) and 0 <= i < n

    s = data["siren"]
    if not ok(s.get("index")):
        raise RuntimeError("Model returned an out-of-range siren index.")
    siren_c = candidates[s["index"]]
    siren = {
        "headline": (s.get("headline") or siren_c["title"]).strip(),
        "dek": (s.get("dek") or "").strip(),
        "quote": "",
        "section": s.get("section") if s.get("section") in SECTION_LABELS else guess_section(siren_c),
        "cands": [siren_c],
    }

    used_primary = {siren_c["link"]}
    entries = []
    for item in data.get("entries", []):
        idxs = [i for i in (item.get("indices") or []) if ok(i)][:4]
        if not idxs:
            continue
        cands = [candidates[i] for i in idxs]
        primary = cands[0]
        if primary["link"] in used_primary:
            continue
        used_primary.add(primary["link"])
        # Secondary links must not repeat the primary.
        seen = {primary["link"]}
        deduped = [primary] + [c for c in cands[1:]
                               if not (c["link"] in seen or seen.add(c["link"]))]
        sec = item.get("section")
        entries.append({
            "headline": (item.get("headline") or primary["title"]).strip(),
            "dek": (item.get("dek") or "").strip(),
            "quote": _verify_quote(item.get("quote") or "", deduped),
            "section": sec if sec in SECTION_LABELS else guess_section(primary),
            "cands": deduped,
        })

    events = []
    for ev in (data.get("events") or [])[:8]:
        idxs = [i for i in (ev.get("indices") or []) if ok(i)][:2]
        when = (ev.get("when") or "").strip()
        what = (ev.get("what") or "").strip()
        if not (idxs and when and what):
            continue
        events.append({"when": when, "what": what,
                       "cands": [candidates[i] for i in idxs]})
    return siren, entries, events


def curate_fallback(candidates):
    """Keyword-only selection when no API key is available: headlines, no deks."""
    scored = []
    for c in candidates:
        t = " " + c["title"].lower() + " "
        if _excluded(t):
            continue
        if not (c.get("social") or any(k in t for k in INCLUDE_KW)):
            continue
        scored.append(c)
    scored = scored[:70]
    if not scored:
        return None, [], []

    def as_entry(c):
        return {"headline": c["title"], "dek": "", "quote": "",
                "section": guess_section(c), "cands": [c]}

    siren = as_entry(scored[0])
    return siren, [as_entry(c) for c in scored[1:]], []


# ---------------------------------------------------------------------------
# Priority names (enforced deterministically, regardless of curation path)
# ---------------------------------------------------------------------------

def _is_priority(entry):
    c = entry["cands"][0]
    return c.get("priority") or any(n in c["title"].lower() for n in PRIORITY_NAMES)


def apply_priority(entries):
    """Float on-subject priority entries the curator KEPT to the front of the
    list (and therefore of their section). The curator decides relevance; this
    only re-ranks what already made the cut."""
    prio = [e for e in entries if _is_priority(e)]
    if not prio:
        return entries
    rest = [e for e in entries if not _is_priority(e)]
    return prio + rest


# ---------------------------------------------------------------------------
# Archive. The main page is always a clean current edition; every curated
# entry is also merged into a persistent store (public/archive.json) and
# rendered as a date-grouped archive page so older stories stay trackable.
# ---------------------------------------------------------------------------

def _load_archive_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("entries", []) if isinstance(data, dict) else []
    except (OSError, ValueError):
        return []


def _load_archive_remote(url):
    """Best-effort fetch of the live published archive, so GitHub Actions
    (fresh checkout) and Mac runs converge on one store."""
    if not url:
        return []
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return data.get("entries", []) if isinstance(data, dict) else []
    except Exception:
        return []


def _merge_archive_item(store, by_id, by_norm, item):
    """Union one archive item into the store, folding near-duplicates."""
    existing = by_id.get(item["id"])
    if existing is None:
        # Same story re-curated later under a different primary link: treat a
        # matching normalized headline within the dedupe window as one story.
        for cand in by_norm.get(item["norm"], []):
            if abs(_date_ord(cand["date"]) - _date_ord(item["date"])) <= ARCHIVE_DEDUPE_DAYS:
                existing = cand
                break
    if existing is None:
        store.append(item)
        by_id[item["id"]] = item
        by_norm.setdefault(item["norm"], []).append(item)
        return 1
    existing["last_seen"] = max(existing.get("last_seen", 0), item["last_seen"])
    existing["siren"] = existing.get("siren") or item.get("siren", False)
    if item.get("dek"):
        existing["dek"] = item["dek"]
    if item.get("quote"):
        existing["quote"] = item["quote"]
    have = {s["link"] for s in existing.get("sources", [])}
    for s in item.get("sources", []):
        if s["link"] not in have:
            existing.setdefault("sources", []).append(s)
            have.add(s["link"])
    return 0


def _date_ord(datestr):
    try:
        return datetime.strptime(datestr, "%Y-%m-%d").toordinal()
    except ValueError:
        return 0


def _archive_item(entry, now_epoch, siren=False):
    primary = entry["cands"][0]
    p = primary.get("published")
    date = (datetime.fromtimestamp(calendar.timegm(p), ZoneInfo("America/New_York"))
            .strftime("%Y-%m-%d") if p else
            datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d"))
    return {
        "id": primary["link"],
        "norm": _norm(entry["headline"]),
        "headline": entry["headline"],
        "dek": entry.get("dek", ""),
        "quote": entry.get("quote", ""),
        "section": entry.get("section", DEFAULT_SECTION),
        "date": date,
        "first_seen": now_epoch,
        "last_seen": now_epoch,
        "siren": siren,
        "sources": [{"source": c["source"], "link": c["link"]} for c in entry["cands"]],
    }


def update_archive(siren, entries):
    now_epoch = int(time.time())
    store = _load_archive_file(ARCHIVE_PATH)
    local_ids = {it.get("id") for it in store}
    remote = [it for it in _load_archive_remote(ARCHIVE_REMOTE)
              if it.get("id") not in local_ids]
    # Remote-only items (e.g. Actions ran while this Mac was off) merge in.
    store += remote

    by_id = {it["id"]: it for it in store if it.get("id")}
    by_norm = {}
    for it in store:
        by_norm.setdefault(it.get("norm", ""), []).append(it)

    added = 0
    if siren:
        added += _merge_archive_item(store, by_id, by_norm,
                                     _archive_item(siren, now_epoch, siren=True))
    for e in entries:
        added += _merge_archive_item(store, by_id, by_norm,
                                     _archive_item(e, now_epoch))

    store.sort(key=lambda it: (it.get("date", ""), it.get("first_seen", 0)),
               reverse=True)
    os.makedirs(os.path.dirname(ARCHIVE_PATH) or ".", exist_ok=True)
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "updated": now_epoch, "entries": store}, fh,
                  ensure_ascii=False, indent=0)
    return store, added


# ---------------------------------------------------------------------------
# Render (Drudge aesthetic: single column, <font> tags, no CSS, no JS)
# ---------------------------------------------------------------------------

LINK_COLOR = "#0018a8"    # dark, high-contrast blue for headline links
SIREN_COLOR = "#cc0000"   # red siren
TEXT_COLOR = "#111111"    # near-black body text
META_COLOR = "#555555"    # source names, dates (secondary)
QUOTE_COLOR = "#222222"   # pulled quotes


def link(text, url, color=LINK_COLOR):
    # Inline color with !important so an embedding site's theme can't gray it out.
    return (f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener" '
            f'style="color:{color} !important;text-decoration:underline;">'
            f'{html.escape(text)}</a>')


def _masthead(stamp, archive_href=None):
    lines = [
        '<font face="Georgia, Times New Roman, serif" size="7"><b>THE MAMDANI FILE</b></font>',
        "<br>",
        '<font face="Arial, Helvetica, sans-serif" size="1">'
        "HIS WORDS &middot; HIS ACTIONS &middot; THE RESEARCH &middot; THE DSA "
        "&mdash; TRACKED ALL DAY</font>",
        "<br>",
        f'<font face="Arial, Helvetica, sans-serif" size="1">UPDATED {html.escape(stamp)}'
        + (" &nbsp;&middot;&nbsp; " + link("THE ARCHIVE »", archive_href)
           if archive_href else "")
        + "</font>",
        '<hr width="60%">',
    ]
    return lines


def _archive_masthead(stamp, n_stories, back_href="index_sections.html"):
    return [
        '<font face="Georgia, Times New Roman, serif" size="7"><b>THE MAMDANI FILE</b></font>',
        "<br>",
        '<font face="Arial, Helvetica, sans-serif" size="3"><b>THE ARCHIVE</b></font>',
        "<br>",
        '<font face="Arial, Helvetica, sans-serif" size="1">'
        f"{n_stories} STORIES ON RECORD &middot; UPDATED {html.escape(stamp)}"
        " &nbsp;&middot;&nbsp; " + link("« BACK TO THE LATEST", back_href) + "</font>",
        '<hr width="60%">',
    ]


def _entry_meta(entry):
    primary = entry["cands"][0]
    bits = html.escape(primary["source"])
    d = _date_str(primary)
    if d:
        bits += " &middot; " + html.escape(d)
    return f'<font face="Arial, Helvetica, sans-serif" size="1"><span style="color:{META_COLOR};">({bits})</span></font>'


def _entry_block(entry):
    """One deep-dive entry: headline link, meta, dek, quote, source row."""
    primary = entry["cands"][0]
    out = ['<font face="Georgia, Times New Roman, serif" size="4"><b>'
           + link(entry["headline"], primary["link"]) + "</b></font> "
           + _entry_meta(entry)]
    if entry.get("dek"):
        out.append("<br>")
        out.append(f'<font face="Georgia, Times New Roman, serif" size="3">'
                   f'{html.escape(entry["dek"])}</font>')
    if entry.get("quote"):
        q = entry["quote"].strip().strip('"“”')
        out.append("<br>")
        out.append(f'<font face="Georgia, Times New Roman, serif" size="3" '
                   f'color="{QUOTE_COLOR}"><i>&ldquo;{html.escape(q)}&rdquo;</i></font>')
    more = entry["cands"][1:]
    if more:
        links = " | ".join(link(c["source"], c["link"]) for c in more)
        out.append("<br>")
        out.append(f'<font face="Arial, Helvetica, sans-serif" size="1">'
                   f'<span style="color:{META_COLOR};">MORE:</span> {links}</font>')
    return "\n".join(out)


def _siren_block(siren):
    if not siren:
        return []
    primary = siren["cands"][0]
    lines = [
        '<font face="Arial, Helvetica, sans-serif" size="5" color="#cc0000"><b>',
        "&#128680;&#128680;&#128680; "
        + link(siren["headline"].upper(), primary["link"], SIREN_COLOR)
        + " &#128680;&#128680;&#128680;",
        "</b></font>",
        "<br>",
    ]
    if siren.get("dek"):
        lines += [f'<font face="Georgia, Times New Roman, serif" size="3">'
                  f'{html.escape(siren["dek"])}</font>', "<br>"]
    lines += [_entry_meta(siren), '<hr width="60%">']
    return lines


def _heading(text):
    return [
        f'<font face="Arial, Helvetica, sans-serif" size="3"><b>{text}</b></font>',
        '<hr width="40%">',
    ]


def _events_block(events):
    """Compact UPCOMING board: dated one-liners with their sources."""
    if not events:
        return []
    lines = _heading("&#128197; UPCOMING")
    lines.append('<table width="100%" style="max-width:680px" border="0" '
                 'cellpadding="0" cellspacing="0"><tr><td align="left">')
    for ev in events:
        srcs = " | ".join(link(c["source"], c["link"]) for c in ev["cands"])
        lines.append(
            f'<font face="Georgia, Times New Roman, serif" size="3">'
            f'<b>{html.escape(ev["when"].upper())}</b> &mdash; '
            f'{html.escape(ev["what"])}</font> '
            f'<font face="Arial, Helvetica, sans-serif" size="1">'
            f'<span style="color:{META_COLOR};">({srcs})</span></font>'
        )
        lines.append("<br>")
    lines += ["</td></tr></table>", '<hr width="60%">']
    return lines


def _entry_table(entries):
    out = ['<table width="100%" style="max-width:680px" border="0" cellpadding="0" '
           'cellspacing="0"><tr><td align="left">']
    for i, e in enumerate(entries):
        out.append(_entry_block(e))
        if i < len(entries) - 1:
            out.append("<br><br>")
    out += ["</td></tr></table>"]
    return out


def _footer():
    return [
        '<hr width="60%">',
        '<font face="Arial, Helvetica, sans-serif" size="1" color="#777777">'
        "Automated aggregation and summarization; summaries are drawn from the "
        "linked sources, and quotes appear verbatim as published. Links open "
        "at their original publishers.</font>",
        "<br><br>",
    ]


# Wrap everything so text without its own color stays dark inside a host page's theme.
WRAP_OPEN = f'<div style="color:{TEXT_COLOR};">'
WRAP_CLOSE = "</div>"


def _content(siren, entries, events, stamp, archive_href):
    """Flat single-column layout (ranked, no section headings)."""
    lines = [WRAP_OPEN, "<center>"] + _masthead(stamp, archive_href)
    lines += _siren_block(siren) + _events_block(events)
    lines += _entry_table(entries)
    lines += _footer() + ["</center>", WRAP_CLOSE]
    return "\n".join(lines)


def _content_sections(siren, entries, events, stamp, archive_href):
    """Sectioned layout (Words / Official / Political / Research / DSA / Reaction)."""
    lines = [WRAP_OPEN, "<center>"] + _masthead(stamp, archive_href)
    lines += _siren_block(siren) + _events_block(events)
    for key in SECTION_ORDER:
        group = [e for e in entries if e.get("section", DEFAULT_SECTION) == key]
        if group:
            lines += _heading(SECTION_LABELS[key])
            lines += _entry_table(group)
            lines += ["<br>"]
    lines += _footer() + ["</center>", WRAP_CLOSE]
    return "\n".join(lines)


# --- Archive page -----------------------------------------------------------

def _archive_entry_block(item):
    """Archived entry: like a live entry, plus a section chip in the meta."""
    sources = item.get("sources") or [{"source": "News", "link": item["id"]}]
    primary = sources[0]
    chip = SECTION_LABELS.get(item.get("section", ""), "")   # already escaped caps
    meta_bits = html.escape(primary["source"])
    if chip:
        meta_bits += " &middot; " + chip
    prefix = "&#128680; " if item.get("siren") else ""
    out = [f'<font face="Georgia, Times New Roman, serif" size="4"><b>{prefix}'
           + link(item["headline"], primary["link"]) + "</b></font> "
           + f'<font face="Arial, Helvetica, sans-serif" size="1">'
             f'<span style="color:{META_COLOR};">({meta_bits})</span></font>']
    if item.get("dek"):
        out.append("<br>")
        out.append(f'<font face="Georgia, Times New Roman, serif" size="3">'
                   f'{html.escape(item["dek"])}</font>')
    if item.get("quote"):
        q = item["quote"].strip().strip('"“”')
        out.append("<br>")
        out.append(f'<font face="Georgia, Times New Roman, serif" size="3" '
                   f'color="{QUOTE_COLOR}"><i>&ldquo;{html.escape(q)}&rdquo;</i></font>')
    more = sources[1:]
    if more:
        links = " | ".join(link(s["source"], s["link"]) for s in more)
        out.append("<br>")
        out.append(f'<font face="Arial, Helvetica, sans-serif" size="1">'
                   f'<span style="color:{META_COLOR};">MORE:</span> {links}</font>')
    return "\n".join(out)


def _archive_date_heading(datestr):
    try:
        label = (datetime.strptime(datestr, "%Y-%m-%d")
                 .strftime("%A, %B %-d, %Y").upper())
    except ValueError:
        label = datestr
    return [
        f'<font face="Arial, Helvetica, sans-serif" size="3"><b>{html.escape(label)}</b></font>',
        '<hr width="40%">',
    ]


def _content_archive(store, stamp, back_href):
    cutoff = (datetime.now(ZoneInfo("America/New_York")).toordinal()
              - ARCHIVE_RENDER_DAYS)
    shown = [it for it in store if _date_ord(it.get("date", "")) >= cutoff]
    lines = [WRAP_OPEN, "<center>"] + _archive_masthead(stamp, len(store), back_href)
    by_date = {}
    for it in shown:
        by_date.setdefault(it.get("date", ""), []).append(it)
    sec_rank = {k: i for i, k in enumerate(SECTION_ORDER)}
    for datestr in sorted(by_date, reverse=True):
        group = sorted(by_date[datestr],
                       key=lambda it: (not it.get("siren"),
                                       sec_rank.get(it.get("section"), 99)))
        lines += _archive_date_heading(datestr)
        lines.append('<table width="100%" style="max-width:680px" border="0" '
                     'cellpadding="0" cellspacing="0"><tr><td align="left">')
        for i, it in enumerate(group):
            lines.append(_archive_entry_block(it))
            if i < len(group) - 1:
                lines.append("<br><br>")
        lines += ["</td></tr></table>", "<br>"]
    if len(store) > len(shown):
        lines.append(f'<font face="Arial, Helvetica, sans-serif" size="1" color="#777777">'
                     f'Showing the last {ARCHIVE_RENDER_DAYS} days; '
                     f'{len(store) - len(shown)} older stories remain on file in archive.json.</font>')
        lines.append("<br>")
    lines += _footer() + ["</center>", WRAP_CLOSE]
    return "\n".join(lines)


def _wrap_full(content, title="THE MAMDANI FILE"):
    return "\n".join([
        "<html>", "<head>", '<meta charset="utf-8">',
        f"<title>{title}</title>",
        # Machine-readable build time (Unix epoch). The deploy workflow's
        # freshness guard reads this to decide whether a probe should rebuild.
        f"<!-- build_epoch={int(time.time())} -->",
        # Classic Drudge auto-refresh (plain HTML, no JS): reload every 10 minutes.
        '<meta http-equiv="refresh" content="600">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "</head>",
        '<body bgcolor="#ffffff" text="#000000" link="#0000cc" vlink="#551a8b">',
        content,
        # Lets an embedding page auto-size its iframe to this content. Harmless
        # when viewed directly (it posts to a parent that isn't listening).
        '<script>(function(){function h(){try{parent.postMessage('
        '{mdt:1,h:document.documentElement.scrollHeight},"*");}catch(e){}}'
        'window.addEventListener("load",h);window.addEventListener("resize",h);'
        'setInterval(h,1500);})();</script>',
        "</body>", "</html>",
    ])


def _wrap_embed(content, stamp):
    return (f"<!-- The Mamdani File - generated {stamp} -->\n"
            f"<!-- build_epoch={int(time.time())} -->\n" + content)


def render_full(siren, entries, events, stamp):
    return _wrap_full(_content(siren, entries, events, stamp, "archive.html"))


def render_embed(siren, entries, events, stamp):
    return _wrap_embed(_content(siren, entries, events, stamp, ARCHIVE_PUBLIC_URL), stamp)


def render_full_sections(siren, entries, events, stamp):
    return _wrap_full(_content_sections(siren, entries, events, stamp, "archive.html"))


def render_embed_sections(siren, entries, events, stamp):
    return _wrap_embed(_content_sections(siren, entries, events, stamp, ARCHIVE_PUBLIC_URL), stamp)


def render_archive_full(store, stamp):
    return _wrap_full(_content_archive(store, stamp, "index_sections.html"),
                      title="THE MAMDANI FILE &mdash; ARCHIVE")


def render_archive_embed(store, stamp):
    # Embedded archive links back to the page hosting the latest edition.
    return _wrap_embed(_content_archive(store, stamp, MAIN_PUBLIC_URL), stamp)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    candidates = gather()
    print(f"Gathered {len(candidates)} unique candidates.", file=sys.stderr)
    if not candidates:
        print("No candidates fetched; aborting.", file=sys.stderr)
        sys.exit(1)

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            siren, entries, events = curate_llm(candidates)
            print(f"LLM built siren + {len(entries)} entries + {len(events)} events.",
                  file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 — keep the page building
            print(f"LLM curation failed ({exc}); using keyword fallback.", file=sys.stderr)
            siren, entries, events = curate_fallback(candidates)
    else:
        print("No ANTHROPIC_API_KEY; using keyword fallback.", file=sys.stderr)
        siren, entries, events = curate_fallback(candidates)

    if not siren:
        print("Nothing in scope after curation; aborting.", file=sys.stderr)
        sys.exit(1)

    # Float Gerard Filitti's on-subject coverage to the front of its section.
    entries = apply_priority(entries)

    # Fold this edition into the permanent archive (main page stays current-only).
    store, added = update_archive(siren, entries)

    stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%a %b %-d, %Y %-I:%M %p ET")
    out_dir = os.path.dirname(OUTPUT_PATH) or "."
    os.makedirs(out_dir, exist_ok=True)

    outputs = {
        OUTPUT_PATH: render_full(siren, entries, events, stamp),                          # flat, full page
        os.path.join(out_dir, "embed.html"): render_embed(siren, entries, events, stamp), # flat fragment
        os.path.join(out_dir, "index_sections.html"):
            render_full_sections(siren, entries, events, stamp),                          # sectioned, full
        os.path.join(out_dir, "embed_sections.html"):
            render_embed_sections(siren, entries, events, stamp),                         # sectioned fragment
        os.path.join(out_dir, "archive.html"): render_archive_full(store, stamp),         # archive, full
        os.path.join(out_dir, "embed_archive.html"): render_archive_embed(store, stamp),  # archive fragment
    }
    for path, content in outputs.items():
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    by_sec = {k: sum(1 for e in entries if e.get("section", DEFAULT_SECTION) == k)
              for k in SECTION_ORDER}
    tally = " / ".join(f"{k}:{by_sec[k]}" for k in SECTION_ORDER)
    quoted = sum(1 for e in entries if e.get("quote"))
    multi = sum(1 for e in entries if len(e["cands"]) > 1)
    xposts = sum(1 for c in candidates if c.get("stag") == "X-POST")
    print(f"Wrote {len(outputs)} files: siren + {len(entries)} entries "
          f"({multi} multi-source, {quoted} with verified quotes), "
          f"{len(events)} upcoming events, {xposts} X posts ingested. "
          f"Archive: +{added} new, {len(store)} total. Sections — {tally}.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
