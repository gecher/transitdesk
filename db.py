import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("bookings.db")

BOOKINGS = [  # ref, passenger, hotel, night, status, pickup, onward flight
    ("ET-5520", "Sara Kebede", "Skylight Hotel", "2026-11-20", "CONFIRMED", "22:30", "ET500 to Washington"),
    ("ET-3301", "Daniel Mekonnen", "Golden Tulip", "2026-11-20", "CONFIRMED", "19:00", "ET302 to Nairobi"),
    ("ET-4471", "Liya Tesfaye", "Skylight Hotel", "2026-11-21", "PENDING", None, "ET700 to Dubai"),
    ("ET-9910", "Michael Brown", "Haile Grand", "2026-11-19", "CANCELLED", None, "ET612 to Toronto"),
]
HOTELS = [  # name, location, shuttle, phone (fake)
    ("Skylight Hotel", "Next to Bole Airport", "Free shuttle every 30 min from Arrivals Gate B, 24h", "+000-555-0101"),
    ("Golden Tulip", "Bole Road, 3 km from airport", "Shuttle at the fixed pickup time from the transfer desk", "+000-555-0102"),
    ("Haile Grand", "Bole area, 5 km from airport", "Taxi voucher from the transfer desk", "+000-555-0103"),
]


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.executescript("""
            DROP TABLE IF EXISTS bookings; DROP TABLE IF EXISTS hotels;
            CREATE TABLE bookings (ref TEXT PRIMARY KEY, passenger TEXT, hotel TEXT,
                night TEXT, status TEXT, pickup_time TEXT, onward_flight TEXT);
            CREATE TABLE hotels (name TEXT PRIMARY KEY, location TEXT, shuttle TEXT, phone TEXT);
        """)
        con.executemany("INSERT INTO bookings VALUES (?,?,?,?,?,?,?)", BOOKINGS)
        con.executemany("INSERT INTO hotels VALUES (?,?,?,?)", HOTELS)


def query(sql: str, params: tuple = ()) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, params)]


if __name__ == "__main__":
    init_db()
    print(f"Created {DB_PATH.name}: {len(BOOKINGS)} bookings, {len(HOTELS)} hotels")