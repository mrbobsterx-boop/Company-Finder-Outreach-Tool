"""Thin data-access layer over the SQLite schema.

Every read/write the rest of the app needs goes through here, so the CLI,
compliance filters, and tests all agree on one definition of "already
contacted" / "already unsubscribed".
"""
from __future__ import annotations

import sqlite3
from typing import Iterable, Optional

from storage.models import Company, Contact, OutreachLogEntry


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ---------------------------------------------------------------- companies
    def upsert_company(self, company: Company) -> int:
        """Insert a company, or update it in place if its osm_id already exists.

        osm_id is how re-running `discover` on the same area avoids creating
        duplicate rows.
        """
        if company.osm_id:
            existing = self.conn.execute(
                "SELECT id FROM companies WHERE osm_id = ?", (company.osm_id,)
            ).fetchone()
            if existing:
                self.conn.execute(
                    """UPDATE companies SET name=?, website=?, address=?, city=?,
                       region=?, country=?, lat=?, lon=?, category=?
                       WHERE id=?""",
                    (
                        company.name, company.website, company.address, company.city,
                        company.region, company.country, company.lat, company.lon,
                        company.category, existing["id"],
                    ),
                )
                self.conn.commit()
                return existing["id"]

        cursor = self.conn.execute(
            """INSERT INTO companies (name, website, address, city, region, country,
               lat, lon, osm_id, category)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                company.name, company.website, company.address, company.city,
                company.region, company.country, company.lat, company.lon,
                company.osm_id, company.category,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_company(self, company_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()

    def list_companies(
        self, only_with_website: bool = False, only_without_contacts: bool = False
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM companies WHERE 1=1"
        if only_with_website:
            query += " AND website IS NOT NULL AND website != ''"
        if only_without_contacts:
            query += (
                " AND id NOT IN (SELECT company_id FROM contacts "
                "WHERE email IS NOT NULL OR phone IS NOT NULL)"
            )
        return self.conn.execute(query).fetchall()

    def count_companies(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS c FROM companies").fetchone()["c"]

    # ----------------------------------------------------------------- contacts
    def add_contact(self, contact: Contact) -> int:
        cursor = self.conn.execute(
            """INSERT INTO contacts (company_id, email, phone, source_page, confidence)
               VALUES (?, ?, ?, ?, ?)""",
            (
                contact.company_id, contact.email, contact.phone,
                contact.source_page, contact.confidence,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_contacts_for_company(self, company_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM contacts WHERE company_id = ?", (company_id,)
        ).fetchall()

    def has_contact(self, company_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM contacts WHERE company_id = ? "
            "AND (email IS NOT NULL OR phone IS NOT NULL) LIMIT 1",
            (company_id,),
        ).fetchone()
        return row is not None

    def list_verified_contacts(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT companies.*, contacts.email AS contact_email,
                      contacts.phone AS contact_phone, contacts.confidence
               FROM contacts JOIN companies ON companies.id = contacts.company_id
               WHERE contacts.email IS NOT NULL"""
        ).fetchall()

    # ------------------------------------------------------------- outreach_log
    def log_outreach(self, entry: OutreachLogEntry) -> int:
        cursor = self.conn.execute(
            """INSERT INTO outreach_log (company_id, email, status, sent_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (entry.company_id, entry.email, entry.status),
        )
        self.conn.commit()
        return cursor.lastrowid

    def last_sent_at(self, email: str) -> Optional[str]:
        row = self.conn.execute(
            """SELECT sent_at FROM outreach_log
               WHERE email = ? AND status = 'sent'
               ORDER BY sent_at DESC LIMIT 1""",
            (email,),
        ).fetchone()
        return row["sent_at"] if row else None

    def has_been_sent(self, email: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM outreach_log WHERE email = ? AND status = 'sent' LIMIT 1",
            (email,),
        ).fetchone()
        return row is not None

    def sent_emails(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT email FROM outreach_log WHERE status = 'sent'"
        ).fetchall()
        return {row["email"] for row in rows}

    # ------------------------------------------------------------- unsubscribed
    def unsubscribe(self, email: str, reason: Optional[str] = None) -> None:
        self.conn.execute(
            """INSERT INTO unsubscribed (email, reason) VALUES (?, ?)
               ON CONFLICT(email) DO NOTHING""",
            (email.lower(), reason),
        )
        self.conn.commit()

    def is_unsubscribed(self, email: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM unsubscribed WHERE email = ? LIMIT 1", (email.lower(),)
        ).fetchone()
        return row is not None

    def unsubscribed_emails(self) -> set[str]:
        rows = self.conn.execute("SELECT email FROM unsubscribed").fetchall()
        return {row["email"] for row in rows}

    # --------------------------------------------------------------- scrape_log
    def log_scrape(
        self,
        domain: str,
        url: str,
        status_code: Optional[int],
        duration_ms: Optional[int],
        error: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO scrape_log (domain, url, status_code, duration_ms, error)
               VALUES (?, ?, ?, ?, ?)""",
            (domain, url, status_code, duration_ms, error),
        )
        self.conn.commit()
