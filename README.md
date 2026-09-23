# Company Finder & Outreach Tool

Finds companies by country/region/city/category, scrapes their public
contact info (email, phone, website), and runs a compliant cold-outreach
email campaign — built to run on free data sources and free service tiers
first, with a clear seam for paid upgrades once volume justifies them.

## Architecture

Each concern is its own top-level Python package so a piece can be swapped
without touching the rest:

```
/discovery      — find companies (OpenStreetMap by default)
/enrichment     — scrape each company's site for email/phone
/storage        — SQLite schema + repository
/mailer         — send email (SMTP by default)
/compliance     — filters that run before anything reaches mailer
/cli            — discover / enrich / export / send commands
config.example.yaml
```

`storage` uses SQLite — a single gitignored file, no server needed, fine
for tens/hundreds of thousands of rows. Postgres is not worth the
operational overhead until that stops being true.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp config.example.yaml config.yaml   # then fill in SMTP credentials, etc.
```

`config.yaml` is gitignored — never commit real SMTP credentials or API
keys. Secrets can also be supplied via environment variables:
`COMPANY_FINDER_SMTP_USERNAME`, `COMPANY_FINDER_SMTP_PASSWORD`,
`COMPANY_FINDER_ANTHROPIC_API_KEY`.

## GUI (local, button-driven)

If you don't want to type CLI flags, run the same functionality from a
local web UI instead:

```bash
streamlit run gui/app.py       # or: ./run_gui.sh
```

This opens `http://localhost:8501` in your browser. Everything runs on
your own machine — it's a UI on top of the same `discovery` /
`enrichment` / `storage` / `compliance` / `mailer` packages the CLI uses,
not a hosted service. It gives you: a discover form, an enrich button with
a progress bar, CSV export with a download button, a send flow that shows
a dry-run preview before an explicit "send for real" confirmation, tabs to
browse the database, and a settings form that writes to `config.yaml`.

## Usage (CLI)

Run these from the repository root (so the top-level packages resolve):

```bash
python -m cli discover --country DE --region NRW --city Siegburg --category webdev
python -m cli enrich --batch 100
python -m cli export --format csv --only-verified
python -m cli send --template offer_v1.html --limit 50 --dry-run
```

`send` always runs as a dry-run (prints who *would* receive the email)
unless you pass `--live`. There is no way to send for real by accident.

### discover

Geocodes the location with Nominatim, then queries Overpass for
matching businesses (`--category` maps to OSM `shop=*`/`office=*`/
`amenity=*` tags — see `discovery/categories.py`; unknown categories fall
back to matching the string directly against all three). Companies are
deduplicated by OSM id, so re-running `discover` on the same area updates
existing rows instead of creating duplicates.

### enrich

For each company with a website and no contact info yet, fetches the
homepage plus any linked contact/about/impressum pages, and extracts
emails and phone numbers with regex (including common obfuscation like
`name [at] domain [dot] com`). Respects `robots.txt`, rate-limits to one
request/second per domain, and caches fetched HTML on disk so reruns don't
re-download pages.

If regex finds nothing on a contact page, and only then, an optional AI
fallback can run — controlled by `enrichment.ai_fallback.backend` in
config.yaml:

- `off` (default) — never called.
- `local_ollama` — free, calls a local Ollama server.
- `cloud_api` — calls the Anthropic API (cheap, since it only ever
  touches the small remainder of pages regex couldn't parse).

### export

Writes companies (or, with `--only-verified`, only companies with a found
email) to `export.csv`.

### send

Renders a Jinja2 template (`mailer/templates/offer_v1.html` by default,
always includes an unsubscribe link) and sends via SMTP. Every recipient
first passes through `compliance.filter_recipients`, which:

- **excludes unsubscribed addresses** — checked against the `unsubscribed`
  table, and this check is never bypassed, not even by `--force`.
- **excludes personal-email domains** (gmail/yahoo/hotmail/...), keeping
  only business addresses.
- **flags strict-consent countries** (Germany, Italy, etc. by default —
  configurable) as `requires_legal_review` and excludes them unless you
  pass `--allow-strict-countries`.
- **enforces a cooldown** (`compliance.min_days_between_emails`, default
  90 days) per email address, checked against `outreach_log`. `--force`
  bypasses only this cooldown check.

## Cost strategy

A pilot of 1,000–3,000 companies in a single city/category should fit
entirely inside free tiers:

| Stage | Default | Cost |
|---|---|---|
| discover | OSM Overpass + Nominatim | free |
| enrich | own scraper (requests + BeautifulSoup) | free (just runtime) |
| enrich AI fallback | off, or local Ollama | free |
| send | SMTP via a free-tier provider (e.g. Brevo, ~300/day) | free |

Upgrade paths, each isolated behind an interface so nothing else needs to
change:

- **More discovery coverage** — implement `DiscoveryProvider` for Google
  Places, Yelp Fusion, etc. and set `discovery.provider` in config.yaml.
- **JS-heavy sites** — set `enrichment.use_playwright_fallback: true`
  (`pip install playwright`, then `playwright install chromium`).
- **AI fallback for contact extraction** — set
  `enrichment.ai_fallback.backend: cloud_api` and an API key.
- **Higher send volume** — implement `MailProvider` for a paid
  cold-outreach platform (Instantly, Smartlead, ...) and set
  `mailer.provider` in config.yaml.

## Testing

```bash
pytest
```

Covers email/phone regex extraction (including obfuscated addresses) and
the compliance guarantee that `send` without `--force` never re-sends to
an address already in `outreach_log`, and never sends to an unsubscribed
address under any flag combination.

## Legal note

Scraping and cold-emailing public business contact data is subject to
laws that vary by jurisdiction (e.g. GDPR in the EU, CAN-SPAM in the US).
The `compliance` module's defaults are a starting point, not legal
advice — review the strict-country list and your own obligations before
sending real campaigns.
