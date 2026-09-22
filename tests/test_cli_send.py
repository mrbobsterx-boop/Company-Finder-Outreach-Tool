import argparse

import cli.main as cli_main
from mailer.base import SendResult
from storage import Company, Contact, OutreachLogEntry, Repository, init_db


class FakeMailProvider:
    def __init__(self, *args, **kwargs):
        self.sent_to = []

    def send(self, to_email, subject, html_body):
        self.sent_to.append(to_email)
        return SendResult(status="sent")


def _base_config(db_path):
    return {
        "database": {"path": str(db_path)},
        "compliance": {
            "strict_consent_countries": ["DE"],
            "personal_email_domains": ["gmail.com"],
            "min_days_between_emails": 90,
        },
        "mailer": {
            "smtp_host": "unused", "smtp_port": 587, "smtp_username": "",
            "smtp_password": "", "from_email": "me@example.com", "from_name": "Me",
            "unsubscribe_base_url": "https://example.com/unsubscribe",
            "throttle_seconds": 0,
            "templates_dir": "mailer/templates",
        },
    }


def _send_args(**overrides):
    defaults = dict(
        template="offer_v1.html", subject="Subject", offer_text="Offer",
        limit=50, dry_run=False, live=True, force=False, allow_strict_countries=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_send_skips_unsubscribed_and_already_sent(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite3"
    conn = init_db(db_path)
    repo = Repository(conn)

    unsub_company = repo.upsert_company(Company(name="Unsub Co", country="US"))
    repo.add_contact(Contact(company_id=unsub_company, email="blocked@business.com"))
    repo.unsubscribe("blocked@business.com")

    repeat_company = repo.upsert_company(Company(name="Repeat Co", country="US"))
    repo.add_contact(Contact(company_id=repeat_company, email="repeat@business.com"))
    repo.log_outreach(
        OutreachLogEntry(company_id=repeat_company, email="repeat@business.com", status="sent")
    )

    fresh_company = repo.upsert_company(Company(name="Fresh Co", country="US"))
    repo.add_contact(Contact(company_id=fresh_company, email="fresh@business.com"))

    fake_provider = FakeMailProvider()
    monkeypatch.setattr(cli_main, "SMTPMailProvider", lambda **kwargs: fake_provider)

    config = _base_config(db_path)
    cli_main.cmd_send(_send_args(force=False), config)

    assert "blocked@business.com" not in fake_provider.sent_to
    assert "repeat@business.com" not in fake_provider.sent_to
    assert "fresh@business.com" in fake_provider.sent_to


def test_send_force_still_never_sends_to_unsubscribed(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite3"
    conn = init_db(db_path)
    repo = Repository(conn)

    company_id = repo.upsert_company(Company(name="Unsub Co", country="US"))
    repo.add_contact(Contact(company_id=company_id, email="blocked@business.com"))
    repo.unsubscribe("blocked@business.com")

    fake_provider = FakeMailProvider()
    monkeypatch.setattr(cli_main, "SMTPMailProvider", lambda **kwargs: fake_provider)

    config = _base_config(db_path)
    cli_main.cmd_send(_send_args(force=True), config)

    assert "blocked@business.com" not in fake_provider.sent_to


def test_send_dry_run_never_sends(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite3"
    conn = init_db(db_path)
    repo = Repository(conn)

    company_id = repo.upsert_company(Company(name="Fresh Co", country="US"))
    repo.add_contact(Contact(company_id=company_id, email="fresh@business.com"))

    fake_provider = FakeMailProvider()
    monkeypatch.setattr(cli_main, "SMTPMailProvider", lambda **kwargs: fake_provider)

    config = _base_config(db_path)
    cli_main.cmd_send(_send_args(dry_run=True, live=False), config)

    assert fake_provider.sent_to == []
