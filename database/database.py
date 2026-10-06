import os
import re
import sqlite3

folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_FILE = os.path.join(folder, "database.db")


def get_db():
    db = sqlite3.connect(DATABASE_FILE)
    db.row_factory = sqlite3.Row
    return db


def create_tables():
    db = get_db()
    old_tables = [row["name"] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            email TEXT UNIQUE,
            username TEXT UNIQUE,
            password_hash TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE COLLATE NOCASE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS department_years (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_id INTEGER,
            year_no INTEGER,
            class_count INTEGER,
            UNIQUE (department_id, year_no)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE COLLATE NOCASE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS teacher_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            department_id INTEGER,
            year_no INTEGER,
            subject TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_name TEXT,
            room TEXT,
            date TEXT,
            start_time TEXT,
            end_time TEXT,
            status TEXT DEFAULT 'Scheduled',
            period TEXT DEFAULT '',
            department TEXT DEFAULT '',
            year_no INTEGER DEFAULT 0,
            section TEXT DEFAULT '',
            subject TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    columns = [row["name"] for row in db.execute("PRAGMA table_info(bookings)").fetchall()]
    if "period" not in columns:
        db.execute("ALTER TABLE bookings ADD COLUMN period TEXT DEFAULT ''")
    if "department" not in columns:
        db.execute("ALTER TABLE bookings ADD COLUMN department TEXT DEFAULT ''")
    if "year_no" not in columns:
        db.execute("ALTER TABLE bookings ADD COLUMN year_no INTEGER DEFAULT 0")
    if "section" not in columns:
        db.execute("ALTER TABLE bookings ADD COLUMN section TEXT DEFAULT ''")
    if "subject" not in columns:
        db.execute("ALTER TABLE bookings ADD COLUMN subject TEXT DEFAULT ''")

    for row in db.execute("SELECT id, room FROM bookings WHERE department = ''").fetchall():
        match = re.match(r"^([A-Za-z]+)(\d+) (D\d+)$", row["room"] or "")
        if match:
            db.execute("UPDATE bookings SET department = ?, year_no = ?, section = ?, room = '' WHERE id = ?",
                       (match.group(1), int(match.group(2)), match.group(3), row["id"]))

    if "teachers" not in old_tables:
        for row in db.execute("SELECT teacher_name FROM bookings").fetchall():
            for name in (row["teacher_name"] or "").split(","):
                name = " ".join(name.split())
                if name != "":
                    db.execute("INSERT OR IGNORE INTO teachers (name) VALUES (?)", (name,))

    db.commit()
    db.close()
