"""SQLite connection and schema management.

SQLite is a single file, needs no server, and comfortably handles the
tens/hundreds of thousands of rows this project targets. No ORM: the
schema is small and stable enough that raw SQL stays readable.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    website TEXT,
    address TEXT,
    city TEXT,
    region TEXT,
    country TEXT,
    lat REAL,
    lon REAL,
    osm_id TEXT UNIQUE,
    category TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    email TEXT,
    phone TEXT,
    source_page TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    verified_at TEXT
);

CREATE TABLE IF NOT EXISTS outreach_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    status TEXT NOT NULL,
    sent_at TEXT,
    opened_at TEXT,
    unsubscribed_at TEXT
);

CREATE TABLE IF NOT EXISTS unsubscribed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    unsubscribed_at TEXT NOT NULL DEFAULT (datetime('now')),
    reason TEXT
);

CREATE TABLE IF NOT EXISTS scrape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    url TEXT NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_contacts_company_id ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_outreach_company_id ON outreach_log(company_id);
CREATE INDEX IF NOT EXISTS idx_outreach_email ON outreach_log(email);
CREATE INDEX IF NOT EXISTS idx_companies_osm_id ON companies(osm_id);
"""


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the GUI caches this connection as a
    # process-wide singleton (st.cache_resource), and Streamlit runs each
    # script rerun on a fresh thread — sqlite3's default same-thread check
    # would reject that even though nothing here runs concurrently within
    # a single session.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> sqlite3.Connection:
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
