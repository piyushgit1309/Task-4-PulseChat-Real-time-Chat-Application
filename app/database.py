import sqlite3
import os
from contextlib import contextmanager

_RESOLVED_DB_PATH = None

def get_db_path():
    global _RESOLVED_DB_PATH
    if _RESOLVED_DB_PATH:
        return _RESOLVED_DB_PATH
    
    current_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    default_path = "/tmp/pulsechat.db" if os.environ.get("VERCEL") else os.path.join(current_dir, "chat.db")
    candidate = os.environ.get("DB_PATH", default_path)
    try:
        conn = sqlite3.connect(candidate)
        conn.execute("CREATE TABLE IF NOT EXISTS _fs_test (id INT);")
        conn.execute("DROP TABLE IF EXISTS _fs_test;")
        conn.commit()
        conn.close()
        _RESOLVED_DB_PATH = candidate
    except Exception:
        fallback_path = "/tmp/pulsechat.db"
        conn = sqlite3.connect(fallback_path)
        conn.close()
        _RESOLVED_DB_PATH = fallback_path
        
    return _RESOLVED_DB_PATH

@contextmanager
def get_db():
    db_file = get_db_path()
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            display_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            avatar_color TEXT DEFAULT '#6366f1',
            bio TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Sessions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        );
        """)
        
        # Rooms table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_direct INTEGER DEFAULT 0,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Room memberships
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS room_members (
            room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (room_id, user_id)
        );
        """)
        
        # Messages table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            recipient_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            content TEXT NOT NULL,
            message_type TEXT DEFAULT 'text',
            file_url TEXT DEFAULT NULL,
            file_name TEXT DEFAULT NULL,
            file_size INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Seed default default public rooms if not exist
        default_rooms = [
            ("general", "General Discussion", "Welcome channel for all team members"),
            ("tech-talk", "Tech Talk", "Full stack web development, architectures & coding"),
            ("project-hub", "Project Hub", "Internship deliverables, reviews and milestones"),
            ("random", "Random & Fun", "Casual water-cooler chats, memes and hobbies")
        ]
        for room_id, name, desc in default_rooms:
            cursor.execute("SELECT id FROM rooms WHERE id = ?", (room_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO rooms (id, name, description, is_direct) VALUES (?, ?, ?, 0)",
                    (room_id, name, desc)
                )

# --- Database Access Helpers ---

def create_user(username, display_name, email, password_hash, salt, avatar_color="#6366f1", bio=""):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, display_name, email, password_hash, salt, avatar_color, bio)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, display_name, email, password_hash, salt, avatar_color, bio))
        user_id = cursor.lastrowid
        # Automatically join default rooms
        for r_id in ["general", "tech-talk", "project-hub", "random"]:
            cursor.execute("INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?, ?)", (r_id, user_id))
        return user_id

def get_user_by_username(username):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cursor.fetchone()

def get_user_by_email(email):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        return cursor.fetchone()

def get_user_by_id(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, display_name, email, avatar_color, bio, created_at, last_seen FROM users WHERE id = ?", (user_id,))
        return cursor.fetchone()

def get_all_users():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, display_name, email, avatar_color, bio, created_at, last_seen FROM users ORDER BY display_name ASC")
        return cursor.fetchall()

def update_user_last_seen(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))

def create_session(token, user_id, expires_at):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expires_at))

def get_session(token):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, u.id as id, u.id as user_id, u.username, u.display_name, u.email, u.avatar_color, u.bio
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ? AND datetime(s.expires_at) > datetime('now')
        """, (token,))
        return cursor.fetchone()

def delete_session(token):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))

def get_rooms():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, COUNT(DISTINCT m.id) as message_count,
                   (SELECT COUNT(*) FROM room_members rm WHERE rm.room_id = r.id) as member_count
            FROM rooms r
            LEFT JOIN messages m ON r.id = m.room_id
            WHERE r.is_direct = 0
            GROUP BY r.id
            ORDER BY r.created_at ASC
        """)
        return cursor.fetchall()

def get_room_by_id(room_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        return cursor.fetchone()

def create_room(room_id, name, description, is_direct=0, created_by=None):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO rooms (id, name, description, is_direct, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (room_id, name, description, is_direct, created_by))
        if created_by:
            cursor.execute("INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?, ?)", (room_id, created_by))

def join_room(room_id, user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?, ?)", (room_id, user_id))

def get_or_create_dm_room(user1_id, user2_id):
    u_min, u_max = min(user1_id, user2_id), max(user1_id, user2_id)
    room_id = f"dm_{u_min}_{u_max}"
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        room = cursor.fetchone()
        if not room:
            cursor.execute("SELECT display_name FROM users WHERE id = ?", (user1_id,))
            u1_row = cursor.fetchone()
            u1_name = u1_row["display_name"] if u1_row else f"User {user1_id}"
            cursor.execute("SELECT display_name FROM users WHERE id = ?", (user2_id,))
            u2_row = cursor.fetchone()
            u2_name = u2_row["display_name"] if u2_row else f"User {user2_id}"
            cursor.execute("""
                INSERT INTO rooms (id, name, description, is_direct, created_by)
                VALUES (?, ?, ?, 1, ?)
            """, (room_id, f"{u1_name} & {u2_name}", "Private Conversation", user1_id))
            cursor.execute("INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?, ?)", (room_id, user1_id))
            cursor.execute("INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?, ?)", (room_id, user2_id))
            cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
            room = cursor.fetchone()
        return room

def create_message(room_id, sender_id, content, recipient_id=None, message_type='text', file_url=None, file_name=None, file_size=None):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (room_id, sender_id, recipient_id, content, message_type, file_url, file_name, file_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (room_id, sender_id, recipient_id, content, message_type, file_url, file_name, file_size))
        msg_id = cursor.lastrowid
        cursor.execute("""
            SELECT m.*, u.username as sender_username, u.display_name as sender_name, u.avatar_color as sender_avatar
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.id = ?
        """, (msg_id,))
        return cursor.fetchone()

def get_room_messages(room_id, limit=100, offset=0):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.*, u.username as sender_username, u.display_name as sender_name, u.avatar_color as sender_avatar
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.room_id = ?
            ORDER BY m.created_at ASC, m.id ASC
            LIMIT ? OFFSET ?
        """, (room_id, limit, offset))
        return cursor.fetchall()
