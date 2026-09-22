import pytest

from compliance.filters import RecipientCandidate, filter_recipients
from storage import Company, OutreachLogEntry, Repository, init_db

COMPLIANCE_CONFIG = {
    "strict_consent_countries": ["DE"],
    "personal_email_domains": ["gmail.com"],
    "min_days_between_emails": 90,
}


@pytest.fixture
def repo(tmp_path):
    conn = init_db(tmp_path / "test.sqlite3")
    return Repository(conn)


def _make_company(repo, name="Acme", country="US") -> int:
    return repo.upsert_company(Company(name=name, country=country))


class TestFilterRecipients:
    def test_unsubscribed_email_is_never_sendable_even_with_force(self, repo):
        company_id = _make_company(repo)
        repo.unsubscribe("unsub@business.com")
        candidates = [
            RecipientCandidate(company_id, "Acme", "US", "unsub@business.com")
        ]

        for force in (False, True):
            decisions = filter_recipients(candidates, repo, COMPLIANCE_CONFIG, force=force)
            assert decisions[0].allowed is False
            assert "unsubscribed" in decisions[0].reasons

    def test_already_sent_recently_is_blocked_without_force(self, repo):
        company_id = _make_company(repo)
        repo.log_outreach(
            OutreachLogEntry(company_id=company_id, email="repeat@business.com", status="sent")
        )
        candidates = [
            RecipientCandidate(company_id, "Acme", "US", "repeat@business.com")
        ]

        decisions = filter_recipients(candidates, repo, COMPLIANCE_CONFIG, force=False)
        assert decisions[0].allowed is False
        assert "frequency_limit" in decisions[0].reasons

    def test_force_bypasses_frequency_limit_but_not_unsubscribe(self, repo):
        company_id = _make_company(repo)
        repo.log_outreach(
            OutreachLogEntry(company_id=company_id, email="repeat@business.com", status="sent")
        )
        candidates = [
            RecipientCandidate(company_id, "Acme", "US", "repeat@business.com")
        ]

        decisions = filter_recipients(candidates, repo, COMPLIANCE_CONFIG, force=True)
        assert decisions[0].allowed is True

    def test_personal_email_domain_is_excluded(self, repo):
        company_id = _make_company(repo)
        candidates = [
            RecipientCandidate(company_id, "Acme", "US", "someone@gmail.com")
        ]
        decisions = filter_recipients(candidates, repo, COMPLIANCE_CONFIG)
        assert decisions[0].allowed is False
        assert "personal_email_domain" in decisions[0].reasons

    def test_strict_country_requires_legal_review_by_default(self, repo):
        company_id = _make_company(repo, country="DE")
        candidates = [
            RecipientCandidate(company_id, "Acme GmbH", "DE", "info@acme.de")
        ]
        decisions = filter_recipients(candidates, repo, COMPLIANCE_CONFIG)
        assert decisions[0].allowed is False
        assert "requires_legal_review" in decisions[0].reasons

    def test_strict_country_allowed_with_explicit_flag(self, repo):
        company_id = _make_company(repo, country="DE")
        candidates = [
            RecipientCandidate(company_id, "Acme GmbH", "DE", "info@acme.de")
        ]
        decisions = filter_recipients(
            candidates, repo, COMPLIANCE_CONFIG, allow_strict_countries=True
        )
        assert decisions[0].allowed is True

    def test_clean_business_email_is_allowed(self, repo):
        company_id = _make_company(repo)
        candidates = [
            RecipientCandidate(company_id, "Acme", "US", "info@acme.com")
        ]
        decisions = filter_recipients(candidates, repo, COMPLIANCE_CONFIG)
        assert decisions[0].allowed is True
        assert decisions[0].reasons == []
