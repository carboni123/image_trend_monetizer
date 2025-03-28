# backend/database.py
import psycopg2
import psycopg2.extras # To get dict-like rows
import os
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv() # Load .env variables

# --- Database Connection Details from Environment Variables ---
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "db") # Default to service name 'db'
DB_PORT = os.getenv("DB_PORT", "5432") # Default Postgres port

# --- Check if essential DB variables are set ---
if not all([DB_NAME, DB_USER, DB_PASSWORD]):
    print("\n*** WARNING: DB_NAME, DB_USER, or DB_PASSWORD not found in environment variables. Database connection will likely fail. ***\n")

# Construct the Database Connection String (DSN)
DSN = f"dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}' host='{DB_HOST}' port='{DB_PORT}'"

@contextmanager
def get_db_connection():
    """Provides a PostgreSQL database connection and cursor context."""
    conn = None # Initialize conn to None
    try:
        # print(f"Attempting to connect to PostgreSQL with DSN: dbname='{DB_NAME}' user='{DB_USER}' host='{DB_HOST}' port='{DB_PORT}'") # Debugging
        conn = psycopg2.connect(DSN)
        # Use RealDictCursor to get rows as dictionaries
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield conn, cur # Provide both connection and cursor
    except psycopg2.OperationalError as e:
         print(f"ERROR: Could not connect to PostgreSQL database '{DB_NAME}' on {DB_HOST}:{DB_PORT} as user '{DB_USER}'. Error: {e}")
         # Depending on your error handling strategy, you might raise the exception
         # or handle it gracefully (e.g., return None or default data)
         raise # Re-raise the exception for Flask/Gunicorn to handle/log
    finally:
        if conn:
            conn.close() # Ensure connection is closed
        # Cursor is automatically closed when 'with' block exits if created by connection

def init_db():
    """Initializes the database schema. Creates table IF NOT EXISTS."""
    print(f"Attempting to ensure DB schema in PostgreSQL database '{DB_NAME}'...")
    try:
        # Connect to check/create table
        with get_db_connection() as (conn, cur):
            cur.execute('''
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    description TEXT,
                    original_image_path TEXT NOT NULL,
                    payment_proof_path TEXT NOT NULL,
                    edited_image_path TEXT,
                    status TEXT NOT NULL DEFAULT 'pending', -- pending, processing, pending_email, completed, error
                    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, -- Use TIMESTAMPTZ for Postgres
                    completed_at TIMESTAMP WITH TIME ZONE
                )
            ''')
            conn.commit() # Commit the table creation
        print(f"DB table 'requests' ensured in PostgreSQL database '{DB_NAME}'.")
    except Exception as e:
        print(f"ERROR during PostgreSQL DB initialization for '{DB_NAME}': {e}")
        # Handle error appropriately - maybe exit if critical?

def add_request(req_id, email, description, original_path, proof_path):
    """Adds a new request to the database."""
    sql = '''INSERT INTO requests (id, email, description, original_image_path, payment_proof_path)
             VALUES (%s, %s, %s, %s, %s)''' # Use %s placeholders for psycopg2
    with get_db_connection() as (conn, cur):
        cur.execute(sql, (req_id, email, description, original_path, proof_path))
        conn.commit()

def get_all_requests():
    """Fetches all requests from the database."""
    with get_db_connection() as (conn, cur):
        cur.execute('SELECT * FROM requests ORDER BY submitted_at DESC')
        requests = cur.fetchall()
        # RealDictCursor already returns list of dicts
        return requests

def update_request_status(req_id, status, edited_path=None):
    """Updates the status and optionally the edited image path of a request."""
    # Determine which fields to update
    if status == 'completed' or status == 'pending_email': # Assume edited_path is set when marking for email/completion
        sql = '''UPDATE requests
                 SET status = %s, edited_image_path = %s, completed_at = CURRENT_TIMESTAMP
                 WHERE id = %s'''
        params = (status, edited_path, req_id)
    else: # For 'processing', 'error', 'pending' - don't update completed_at or edited_path unless explicitly provided
        sql = '''UPDATE requests
                 SET status = %s
                 WHERE id = %s'''
        params = (status, req_id)
         # Optionally handle updating edited_path for other statuses if needed
         # if edited_path is not None:
         #     sql = 'UPDATE requests SET status = %s, edited_image_path = %s WHERE id = %s'
         #     params = (status, edited_path, req_id)

    with get_db_connection() as (conn, cur):
        cur.execute(sql, params)
        conn.commit()
        # Check if update was successful by row count
        return cur.rowcount > 0

def get_request_by_id(req_id):
    """Fetches a single request by its ID."""
    with get_db_connection() as (conn, cur):
        cur.execute('SELECT * FROM requests WHERE id = %s', (req_id,))
        request = cur.fetchone()
        # RealDictCursor returns dict or None
        return request

# --- Initialize DB when module is loaded ---
# This remains a good place to ensure the table exists on startup
print("Initializing DB from database.py module level (PostgreSQL)...")
init_db()
print("DB initialization attempt completed from database.py (PostgreSQL).")