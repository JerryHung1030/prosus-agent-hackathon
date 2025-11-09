# db.py
import os
import sqlite3

# Default to a project-local path to avoid permission issues like '/data/...'
DB_PATH = os.getenv("DB_PATH", "./.data/housing.db")


def get_connection():
    # Ensure parent directory exists before opening the SQLite file
    db_abs_path = os.path.abspath(DB_PATH)
    os.makedirs(os.path.dirname(db_abs_path), exist_ok=True)

    conn = sqlite3.connect(db_abs_path)
    conn.row_factory = sqlite3.Row
    # more stable for concurrent read/write
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db():
    with get_connection() as conn:
        cur = conn.cursor()
        # listings: flatten the fields that need to be queried, the rest is stored in raw_json
        cur.execute(
            """
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
            agency_contact_url TEXT,
            first_seen TEXT,
            pets_allowed INTEGER,
            scraper_version TEXT,
            thumbnail_path TEXT,
            latitude REAL,
            longitude REAL,
            raw_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            application_status TEXT DEFAULT 'none', -- 'none', 'pending', 'applied'
            application_screenshot_path TEXT         -- e.g., 'outputs/submission_proof_xxx.png'
        )
        """
        )

        # Create geo index for faster radius queries
        cur.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_listings_geo ON listings(latitude, longitude)
        """
        )

        # Address geocoding cache to prevent redundant API calls
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS address_cache (
            address_hash TEXT PRIMARY KEY,
            address TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
        )

        # [MODIFIED] Enhance llm_jobs table for asynchronous flow
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS llm_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,            -- 'running', 'finished', 'error'
            start_time TEXT NOT NULL
        )
        """
        )

        # Perform lightweight migrations to add new columns if they don't exist
        cur.execute("PRAGMA table_info(llm_jobs)")
        existing_cols = {row[1] for row in cur.fetchall()}
        migrations: list[tuple[str, str]] = [
            ("session_id", "TEXT"),
            ("job_type", "TEXT"),
            ("result", "TEXT"),
            ("end_time", "TEXT"),
        ]
        for col_name, col_type in migrations:
            if col_name not in existing_cols:
                cur.execute(f"ALTER TABLE llm_jobs ADD COLUMN {col_name} {col_type}")

        # [NEW] Index for faster job lookup by session
        cur.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_llm_jobs_session ON llm_jobs(session_id)
        """
        )

        # [NEW] Migrate listings table to add application status columns if they don't exist
        cur.execute("PRAGMA table_info(listings)")
        existing_listings_cols = {row[1] for row in cur.fetchall()}
        listings_migrations: list[tuple[str, str, str]] = [
            ("application_status", "TEXT", "DEFAULT 'none'"),
            ("application_screenshot_path", "TEXT", ""),
        ]
        for col_name, col_type, col_extra in listings_migrations:
            if col_name not in existing_listings_cols:
                alter_sql = f"ALTER TABLE listings ADD COLUMN {col_name} {col_type} {col_extra}".strip()
                cur.execute(alter_sql)
                print(f"Added column {col_name} to listings table")

        conn.commit()
    print("Database initialized.")
