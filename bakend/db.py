# db.py
import sqlite3
from pathlib import Path

DB_PATH = Path("housing.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # more stable for concurrent read/write
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    with get_connection() as conn:
        cur = conn.cursor()
        # listings: flatten the fields that need to be queried, the rest is stored in raw_json
        cur.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            price_amount INTEGER,
            price_frequency TEXT,
            service_costs INTEGER,
            area_m2 REAL,
            street TEXT,
            neighborhood TEXT,
            city TEXT,
            postal_code TEXT,
            housing_type TEXT,
            furnishes TEXT,
            deposit INTEGER,
            contract_start_date TEXT,
            contract_duration_months INTEGER,
            agency_name TEXT,
            agency_email TEXT,
            first_seen TEXT,
            pets_allowed INTEGER,
            scraper_version TEXT,
            raw_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        conn.commit()
    print("Database initialized.")
