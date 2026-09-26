"""Command-line entry point.

    python -m cli discover --country DE --region NRW --city Siegburg --category webdev
    python -m cli enrich --batch 100
    python -m cli export --format csv --only-verified
    python -m cli send --template offer_v1.html --limit 50 --dry-run

Run from the repository root so the top-level packages (discovery, storage,
...) are importable.
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

from config import load_config
from compliance import RecipientCandidate, filter_recipients
from discovery import OSMDiscoveryProvider
from enrichment.scraper import CompanyScraper
from mailer import SMTPMailProvider
from mailer.templating import build_unsubscribe_url, render_template
from storage import Company, Contact, OutreachLogEntry, Repository, init_db

logger = logging.getLogger("cli")


def _repository(config: dict) -> Repository:
    conn = init_db(config["database"]["path"])
    return Repository(conn)


# --------------------------------------------------------------------- discover
def cmd_discover(args: argparse.Namespace, config: dict) -> None:
    repo = _repository(config)
    provider = OSMDiscoveryProvider(
        overpass_base_url=config["discovery"]["overpass_base_url"],
        geocoder_base_url=config["discovery"]["geocoder_base_url"],
        user_agent=config["discovery"]["user_agent"],
        request_delay_seconds=config["discovery"]["request_delay_seconds"],
        bbox_radius_km=config["discovery"]["bbox_radius_km"],
    )

    companies = provider.search(
        country=args.country, region=args.region, city=args.city, category=args.category
    )
    # Discovery doesn't know the ISO country code the user typed (it only
    # geocodes a name), so store the CLI's --country value verbatim; it
    # doubles as the phonenumbers region hint during enrichment.
    for company in companies:
        company.country = args.country

    saved = 0
    for company in companies:
        repo.upsert_company(company)
        saved += 1

    print(f"Discovered {len(companies)} companies, saved/updated {saved} in the database.")


# ----------------------------------------------------------------------- enrich
def cmd_enrich(args: argparse.Namespace, config: dict) -> None:
    repo = _repository(config)
    scraper = CompanyScraper(
        contact_page_keywords=config["enrichment"]["contact_page_keywords"],
        user_agent=config["enrichment"]["user_agent"],
        cache_dir=config["enrichment"]["cache_dir"],
        domain_delay_seconds=config["enrichment"]["domain_delay_seconds"],
        min_delay_seconds=config["enrichment"]["min_delay_seconds"],
        max_delay_seconds=config["enrichment"]["max_delay_seconds"],
        request_timeout_seconds=config["enrichment"]["request_timeout_seconds"],
        ai_fallback_config=config["enrichment"]["ai_fallback"],
        repository=repo,
    )

    companies = repo.list_companies(only_with_website=True, only_without_contacts=not args.force)
    batch = companies[: args.batch]

    found = 0
    for row in batch:
        website = row["website"]
        logger.info("Enriching company_id=%s website=%s", row["id"], website)
        result = scraper.scrape_company(website, default_region=row["country"])

        if not result.emails and not result.phones:
            continue

        found += 1
        if result.emails:
            for email in result.emails:
                repo.add_contact(
                    Contact(
                        company_id=row["id"],
                        email=email,
                        phone=result.phones[0] if result.phones else None,
                        source_page=result.source_page,
                        confidence=0.4 if result.used_ai_fallback else 0.9,
                    )
                )
        else:
            repo.add_contact(
                Contact(
                    company_id=row["id"],
                    email=None,
                    phone=result.phones[0],
                    source_page=result.source_page,
                    confidence=0.4 if result.used_ai_fallback else 0.9,
                )
            )

    print(f"Enriched {len(batch)} companies, found contact info for {found}.")


# ----------------------------------------------------------------------- export
def cmd_export(args: argparse.Namespace, config: dict) -> None:
    repo = _repository(config)

    if args.format != "csv":
        print(f"Unsupported export format: {args.format}", file=sys.stderr)
        sys.exit(1)

    if args.only_verified:
        rows = repo.list_verified_contacts()
        fieldnames = [
            "id", "name", "website", "address", "city", "region", "country",
            "category", "contact_email", "contact_phone", "confidence",
        ]
    else:
        rows = repo.list_companies()
        fieldnames = [
            "id", "name", "website", "address", "city", "region", "country",
            "category", "lat", "lon",
        ]

    out_path = Path(args.output) if args.output else Path("export.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})

    print(f"Exported {len(rows)} rows to {out_path}")


# ------------------------------------------------------------------------- send
def cmd_send(args: argparse.Namespace, config: dict) -> None:
    repo = _repository(config)

    candidates = [
        RecipientCandidate(
            company_id=row["id"],
            company_name=row["name"],
            country=row["country"],
            email=row["contact_email"],
        )
        for row in repo.list_verified_contacts()
    ]

    decisions = filter_recipients(
        candidates,
        repository=repo,
        compliance_config=config["compliance"],
        force=args.force,
        allow_strict_countries=args.allow_strict_countries,
    )

    allowed = [d for d in decisions if d.allowed][: args.limit]
    skipped = [d for d in decisions if not d.allowed]

    is_live = args.live and not args.dry_run

    mail_provider = None
    if is_live:
        mail_provider = SMTPMailProvider(
            host=config["mailer"]["smtp_host"],
            port=config["mailer"]["smtp_port"],
            username=config["mailer"]["smtp_username"],
            password=config["mailer"]["smtp_password"],
            from_email=config["mailer"]["from_email"],
            from_name=config["mailer"]["from_name"],
            throttle_seconds=config["mailer"]["throttle_seconds"],
        )

    sent_count = 0
    for decision in allowed:
        candidate = decision.candidate
        unsubscribe_url = build_unsubscribe_url(
            config["mailer"]["unsubscribe_base_url"], candidate.email
        )
        html_body = render_template(
            config["mailer"]["templates_dir"],
            args.template,
            {
                "company_name": candidate.company_name,
                "city": "",
                "offer_text": args.offer_text,
                "sender_name": config["mailer"]["from_name"],
                "unsubscribe_url": unsubscribe_url,
            },
        )

        if not is_live:
            print(f"[DRY RUN] would send to {candidate.email} ({candidate.company_name})")
            continue

        result = mail_provider.send(candidate.email, args.subject, html_body)
        repo.log_outreach(
            OutreachLogEntry(
                company_id=candidate.company_id,
                email=candidate.email,
                status=result.status,
            )
        )
        if result.status == "sent":
            sent_count += 1
        print(f"[{result.status.upper()}] {candidate.email} ({candidate.company_name})")

    print(f"\n{len(allowed)} recipients eligible, {len(skipped)} skipped by compliance filters.")
    if skipped:
        reason_counts: dict[str, int] = {}
        for decision in skipped:
            for reason in decision.reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        for reason, count in reason_counts.items():
            print(f"  - {reason}: {count}")

    if is_live:
        print(f"Sent {sent_count} emails.")
    else:
        print("Dry run only — no emails were sent. Pass --live to send for real.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli", description="Company Finder & Outreach Tool")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_discover = subparsers.add_parser("discover", help="Find companies via OpenStreetMap")
    p_discover.add_argument("--country", required=True, help="e.g. DE")
    p_discover.add_argument("--region", default=None)
    p_discover.add_argument("--city", default=None)
    p_discover.add_argument("--category", required=True, help="e.g. webdev, restaurant, law")
    p_discover.set_defaults(func=cmd_discover)

    p_enrich = subparsers.add_parser("enrich", help="Scrape company websites for contacts")
    p_enrich.add_argument("--batch", type=int, default=100)
    p_enrich.add_argument(
        "--force", action="store_true",
        help="Re-scrape companies that already have contact info",
    )
    p_enrich.set_defaults(func=cmd_enrich)

    p_export = subparsers.add_parser("export", help="Export companies/contacts to CSV")
    p_export.add_argument("--format", default="csv", choices=["csv"])
    p_export.add_argument("--only-verified", action="store_true")
    p_export.add_argument("--output", default=None)
    p_export.set_defaults(func=cmd_export)

    p_send = subparsers.add_parser("send", help="Send the outreach email campaign")
    p_send.add_argument("--template", default="offer_v1.html")
    p_send.add_argument("--subject", default="A quick idea for your business")
    p_send.add_argument(
        "--offer-text", default="We help businesses like yours grow online.",
        help="Body paragraph inserted into the template",
    )
    p_send.add_argument("--limit", type=int, default=50)
    p_send.add_argument(
        "--dry-run", action="store_true",
        help="Show who would receive the email without sending (this is the default)",
    )
    p_send.add_argument(
        "--live", action="store_true",
        help="Actually send emails. Required to send for real; ignored if --dry-run is also passed.",
    )
    p_send.add_argument(
        "--force", action="store_true",
        help="Bypass the frequency-limit cooldown (never bypasses unsubscribes)",
    )
    p_send.add_argument(
        "--allow-strict-countries", action="store_true",
        help="Include recipients in countries flagged as requiring legal review",
    )
    p_send.set_defaults(func=cmd_send)

    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    args.func(args, config)


if __name__ == "__main__":
    main()
