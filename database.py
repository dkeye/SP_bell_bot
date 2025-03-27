import sqlite3

DB_FILE = "users.db"


def init_db():
    """Инициализация базы данных."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                mac TEXT PRIMARY KEY,
                user_id INTEGER,
                username TEXT
            )
        """)
        conn.commit()


def add_user(mac, user_id, username):
    """Добавление нового пользователя."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (mac, user_id, username) VALUES (?, ?, ?)", (mac, user_id, username))
        conn.commit()


def remove_user(mac):
    """Удаление пользователя по MAC-адресу."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE mac = ?", (mac,))
        conn.commit()


def get_user_by_mac(mac):
    """Получение пользователя по MAC-адресу."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mac, user_id, username FROM users WHERE mac = ?", (mac,))
        return cursor.fetchone()


def get_user_by_id(user_id):
    """Получение пользователя по Telegram ID."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mac, user_id, username FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchall()


def get_all_users():
    """Получение всех зарегистрированных пользователей."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mac, user_id, username FROM users")
        return {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
