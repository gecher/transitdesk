"""Fictional demo data for TransitDesk.

Storage:
  - DATABASE_URL set (e.g. Neon Postgres)  -> Postgres  (used on Vercel)
  - not set                                  -> SQLite file bookings.db (local)
The rest of the code always writes SQL with ? placeholders; this module adapts it.
"""
import atexit
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

DB_PATH = Path(__file__).with_name("bookings.db")

STATUSES = ("CONFIRMED", "PENDING", "CANCELLED")

# The first four are used by the evaluation set (eval_set.json). Don't change them.
BOOKINGS = [  # ref, passenger, hotel, night, status, pickup, onward flight
    ("ET-5520", "Sara Kebede", "Skylight Hotel", "2026-11-20", "CONFIRMED", "22:30", "ET500 to Washington"),
    ("ET-3301", "Daniel Mekonnen", "Golden Tulip", "2026-11-20", "CONFIRMED", "19:00", "ET302 to Nairobi"),
    ("ET-4471", "Liya Tesfaye", "Skylight Hotel", "2026-11-21", "PENDING", None, "ET700 to Dubai"),
    ("ET-9910", "Michael Brown", "Haile Grand", "2026-11-19", "CANCELLED", None, "ET612 to Toronto"),
    ("ET-1204", "Amina Yusuf", "Bole Garden Hotel", "2026-11-19", "CONFIRMED", "21:15", "ET858 to Lagos"),
    ("ET-1377", "Kenji Sato", "Skylight Hotel", "2026-11-19", "CONFIRMED", "23:45", "ET672 to Tokyo"),
    ("ET-1580", "Hanna Girma", "Entoto View Inn", "2026-11-20", "PENDING", None, "ET834 to Accra"),
    ("ET-1662", "Lucas Martin", "Golden Tulip", "2026-11-20", "CONFIRMED", "20:30", "ET704 to Paris"),
    ("ET-1745", "Priya Nair", "Skylight Hotel", "2026-11-20", "CONFIRMED", "18:40", "ET688 to Mumbai"),
    ("ET-1893", "Yonas Alemu", "Haile Grand", "2026-11-21", "CONFIRMED", "22:00", "ET306 to Johannesburg"),
    ("ET-2018", "Grace Otieno", "Bole Garden Hotel", "2026-11-21", "CANCELLED", None, "ET880 to Kigali"),
    ("ET-2156", "Omar Haddad", "Skylight Hotel", "2026-11-21", "CONFIRMED", "19:20", "ET410 to Cairo"),
    ("ET-2290", "Chen Wei", "Entoto View Inn", "2026-11-21", "PENDING", None, "ET604 to Guangzhou"),
    ("ET-2341", "Selam Bekele", "Golden Tulip", "2026-11-22", "CONFIRMED", "21:00", "ET500 to Washington"),
    ("ET-2477", "Fatima Diallo", "Skylight Hotel", "2026-11-22", "CONFIRMED", "23:10", "ET908 to Dakar"),
    ("ET-2533", "James Carter", "Haile Grand", "2026-11-22", "PENDING", None, "ET612 to Toronto"),
    ("ET-2689", "Meron Haile", "Bole Garden Hotel", "2026-11-22", "CONFIRMED", "20:05", "ET702 to Frankfurt"),
    ("ET-2714", "Ahmed Karim", "Skylight Hotel", "2026-11-23", "CONFIRMED", "22:50", "ET620 to Riyadh"),
    ("ET-2852", "Elena Rossi", "Entoto View Inn", "2026-11-23", "CANCELLED", None, "ET706 to Rome"),
    ("ET-2967", "Tewodros Asfaw", "Golden Tulip", "2026-11-23", "CONFIRMED", "18:15", "ET314 to Lusaka"),
]

HOTELS = [  # name, location, shuttle, phone (all fake)
    ("Skylight Hotel", "Next to Bole Airport", "Free shuttle every 30 min from Arrivals Gate B, 24h", "+000-555-0101"),
    ("Golden Tulip", "Bole Road, 3 km from airport", "Shuttle at the fixed pickup time from the transfer desk", "+000-555-0102"),
    ("Haile Grand", "Bole area, 5 km from airport", "Taxi voucher from the transfer desk", "+000-555-0103"),
    ("Bole Garden Hotel", "Bole Medhanialem, 4 km from airport", "Shuttle at the fixed pickup time from Arrivals Gate A", "+000-555-0104"),
    ("Entoto View Inn", "Megenagna, 8 km from airport", "Taxi voucher from the transfer desk", "+000-555-0105"),
]


_pool = None


def pool():
    """One shared Postgres connection pool (also used by the LangGraph checkpointer)."""
    global _pool
    if _pool is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(
            DATABASE_URL, min_size=1, max_size=5, open=True,
            check=ConnectionPool.check_connection,      # replace connections closed while idle
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
        atexit.register(_pool.close)                    # exit promptly when a script ends
    return _pool


def _pg(sql: str) -> str:
    """SQLite-style SQL -> Postgres: ? placeholders, case-insensitive LIKE."""
    return sql.replace("?", "%s").replace(" LIKE ", " ILIKE ")


if USE_POSTGRES:
    import psycopg
    IntegrityError = (sqlite3.IntegrityError, psycopg.errors.IntegrityError)
else:
    IntegrityError = (sqlite3.IntegrityError,)


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and return rows as dictionaries."""
    if USE_POSTGRES:
        with pool().connection() as con:
            return [dict(r) for r in con.execute(_pg(sql), params).fetchall()]
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, params)]


def execute(sql: str, params: tuple = ()) -> int:
    """Run INSERT/UPDATE/DELETE and return how many rows changed."""
    if USE_POSTGRES:
        with pool().connection() as con:
            return con.execute(_pg(sql), params).rowcount
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = ON")
        return con.execute(sql, params).rowcount


SCHEMA = [
    "DROP TABLE IF EXISTS bookings",
    "DROP TABLE IF EXISTS hotels",
    "CREATE TABLE hotels (name TEXT PRIMARY KEY, location TEXT, shuttle TEXT, phone TEXT)",
    """CREATE TABLE bookings (ref TEXT PRIMARY KEY, passenger TEXT NOT NULL,
        hotel TEXT NOT NULL REFERENCES hotels(name), night TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('CONFIRMED','PENDING','CANCELLED')),
        pickup_time TEXT, onward_flight TEXT)""",
]


def init_db() -> None:
    """Create the tables and load the demo data (this resets any changes)."""
    for statement in SCHEMA:
        execute(statement)
    for hotel in HOTELS:
        execute("INSERT INTO hotels VALUES (?,?,?,?)", hotel)
    for booking in BOOKINGS:
        execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?)", booking)
    ensure_usage_table()


def ensure_usage_table() -> None:
    """Chat usage log for rate limiting (kept across resets; created if missing)."""
    execute("CREATE TABLE IF NOT EXISTS chat_usage (ip_hash TEXT NOT NULL, at_epoch BIGINT NOT NULL)")


if __name__ == "__main__":
    init_db()
    where = "Postgres (DATABASE_URL)" if USE_POSTGRES else DB_PATH.name
    print(f"Created demo data in {where}: {len(BOOKINGS)} bookings, {len(HOTELS)} hotels")
