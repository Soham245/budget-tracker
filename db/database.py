import os
import sqlite3
from kivy.utils import platform


def get_db_path():
    if platform == 'android':
        from android.storage import app_storage_path
        return os.path.join(app_storage_path(), 'budget.db')
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'budget.db')


def get_connection():
    return sqlite3.connect(get_db_path())


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS categories (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        name   TEXT NOT NULL UNIQUE,
        color  TEXT DEFAULT '#5C6BC0',
        budget REAL DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        amount      REAL NOT NULL,
        category_id INTEGER NOT NULL REFERENCES categories(id),
        note        TEXT DEFAULT '',
        date        TEXT NOT NULL,
        created_at  TEXT DEFAULT (date('now'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS goals (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        target_amount REAL NOT NULL,
        saved_amount  REAL DEFAULT 0,
        deadline      TEXT,
        is_complete   INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )''')

    for name, color in [
        ('Food', '#FF7043'), ('Transport', '#42A5F5'), ('Shopping', '#AB47BC'),
        ('Bills', '#EF5350'), ('Health', '#66BB6A'), ('Entertainment', '#FFCA28'),
        ('Subscriptions', '#7E57C2'), ('Other', '#78909C'),
    ]:
        c.execute('INSERT OR IGNORE INTO categories (name, color) VALUES (?, ?)', (name, color))

    for key, value in [('monthly_income', '0'), ('currency', '₹')]:
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))

    # Recurring feature migration — safe to run on every startup
    for table, col, defn in [
        ('expenses', 'is_recurring',    'INTEGER DEFAULT 0'),
        ('expenses', 'recur_interval',  'INTEGER DEFAULT 1'),
        ('expenses', 'recur_next_date', 'TEXT'),
        ('expenses', 'recur_unit',      "TEXT DEFAULT 'month'"),
        ('expenses', 'recur_paused',    'INTEGER DEFAULT 0'),
        ('expenses', 'recur_start_date','TEXT'),   # anchor: preserves original day-of-month
        ('goals',    'is_recurring',    'INTEGER DEFAULT 0'),
        ('goals',    'recur_amount',    'REAL DEFAULT 0'),
        ('goals',    'recur_interval',  'INTEGER DEFAULT 1'),
        ('goals',    'recur_unit',      "TEXT DEFAULT 'month'"),
        ('goals',    'recur_next_date', 'TEXT'),
    ]:
        try:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {defn}')
        except Exception:
            pass  # column already exists

    conn.commit()
    conn.close()
