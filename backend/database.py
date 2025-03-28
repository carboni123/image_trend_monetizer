import sqlite3
import os
from contextlib import contextmanager

DB_SUBDIR = '/app/database'
DATABASE_PATH = os.path.join(DB_SUBDIR, 'waitlist.db')

@contextmanager
def get_db_connection():
    """Provides a database connection context."""
    # Make sure the directory for the DB exists if needed (though volume mount handles this)
    # os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True) # Optional safety check
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row # Return rows as dict-like objects
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initializes the database schema if it doesn't exist."""
    # Check if the file exists at the container path
    db_dir = os.path.dirname(DATABASE_PATH)
    if not os.path.exists(db_dir):
        print(f"Creating database directory: {db_dir}")
        os.makedirs(db_dir, exist_ok=True) # Ensure directory exists before connecting

    if os.path.exists(DATABASE_PATH):
        print("Database already exists at container path.")
        return

    print("Initializing database at container path...")
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE requests (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                description TEXT,
                original_image_path TEXT NOT NULL,
                payment_proof_path TEXT NOT NULL,
                edited_image_path TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        conn.commit()
    print("Database initialized.")

def add_request(req_id, email, description, original_path, proof_path):
    """Adds a new request to the database."""
    with get_db_connection() as conn:
        conn.execute(
            '''INSERT INTO requests (id, email, description, original_image_path, payment_proof_path)
               VALUES (?, ?, ?, ?, ?)''',
            (req_id, email, description, original_path, proof_path)
        )
        conn.commit()

def get_all_requests():
    """Fetches all requests from the database."""
    with get_db_connection() as conn:
        cursor = conn.execute('SELECT * FROM requests ORDER BY submitted_at DESC')
        requests = cursor.fetchall()
        # Convert Row objects to plain dictionaries for easier serialization/use
        return [dict(row) for row in requests]

def update_request_status(req_id, status, edited_path=None):
    """Updates the status and optionally the edited image path of a request."""
    with get_db_connection() as conn:
        if status == 'completed':
            conn.execute(
                '''UPDATE requests
                   SET status = ?, edited_image_path = ?, completed_at = CURRENT_TIMESTAMP
                   WHERE id = ?''',
                (status, edited_path, req_id)
            )
        else:
             conn.execute(
                '''UPDATE requests
                   SET status = ?, edited_image_path = ?
                   WHERE id = ?''',
                (status, edited_path, req_id)
            )
        conn.commit()
        # Check if update was successful
        return conn.total_changes > 0

def get_request_by_id(req_id):
    """Fetches a single request by its ID."""
    with get_db_connection() as conn:
        cursor = conn.execute('SELECT * FROM requests WHERE id = ?', (req_id,))
        request = cursor.fetchone()
        return dict(request) if request else None

# --- Initialize DB when module is loaded ---
print("Initializing DB from database.py module level...")
init_db()
print("DB initialization attempt completed from database.py.")