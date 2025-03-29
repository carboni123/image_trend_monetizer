# manager_ui_direct_access.py (Modified from old script)

import sys
import os
import posixpath # Use for constructing MinIO keys consistently
import shutil
import requests
import datetime
from contextlib import contextmanager

# --- NEW: Imports for PostgreSQL and MinIO ---
import psycopg2
import psycopg2.extras # To get dict-like rows
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, NoCredentialsError

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QTableView, QLineEdit, QPushButton, QFileDialog, QAbstractItemView,
    QTextEdit, QMessageBox, QSizePolicy, QHeaderView, QMenu
)
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QSortFilterProxyModel, QModelIndex, QDateTime,
    QUrl, QRegularExpression
)
from PyQt6.QtGui import QPixmap, QDesktopServices, QAction, QCursor

# --- Configuration ---
# Backend API endpoint base URL (for sending email) - Needs Port!
API_BASE_URL = 'http://192.168.0.112:5000' # <<< ENSURE PORT IS CORRECT

# --- Database Connection Details (PostgreSQL) ---
# Load from environment or hardcode for testing
DB_NAME = os.getenv("DB_NAME", "image_trend_db")
DB_USER = os.getenv("DB_USER", "trend_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "a_very_secret_pg_password")
DB_HOST = os.getenv("DB_HOST_MANAGER", "192.168.0.112") # IP of host running Postgres
DB_PORT = os.getenv("DB_PORT", "5432")
DSN = f"dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}' host='{DB_HOST}' port='{DB_PORT}'"

# --- MinIO Connection Details ---
# Load from environment or hardcode for testing (Match your .env)
MINIO_ENDPOINT_URL = os.getenv('MINIO_ENDPOINT_URL_MANAGER', 'http://192.168.0.112:9000') # Accessible from UI host
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'HD85kqi0R3ybUeGKAUqV') # From .env
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'tJurvOopvQUKQLQXV0wI2AslCKprURE9Qjpqrng3') # From .env
MINIO_BUCKET_NAME = os.getenv('MINIO_BUCKET_NAME', 'image-uploads') # From .env

# --- Initialize MinIO S3 Client ---
s3_client = None
try:
    print(f"Attempting to connect to MinIO at {MINIO_ENDPOINT_URL}...")
    s3_client = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT_URL,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        # region_name='us-east-1' # Often optional for MinIO but sometimes needed by boto3
    )
    # Test connection - list buckets (optional, requires ListAllMyBuckets permission)
    # s3_client.list_buckets()
    # Or test connection by trying to access the target bucket head
    s3_client.head_bucket(Bucket=MINIO_BUCKET_NAME)
    print(f"Successfully connected to MinIO and accessed bucket '{MINIO_BUCKET_NAME}'.")
except (NoCredentialsError, PartialCredentialsError):
     print("\n*** CRITICAL: MinIO credentials not found or incomplete. Image loading/upload will fail. ***\n")
     QMessageBox.critical(None, "MinIO Error", "MinIO credentials missing or invalid.")
     s3_client = None # Ensure it's None
except ClientError as e:
    if 'NoSuchBucket' in str(e):
        print(f"\n*** CRITICAL: MinIO bucket '{MINIO_BUCKET_NAME}' not found. Create it via MinIO console or setup script. ***\n")
        QMessageBox.critical(None, "MinIO Error", f"Bucket '{MINIO_BUCKET_NAME}' not found.")
    elif 'AccessDenied' in str(e):
         print(f"\n*** CRITICAL: Access Denied connecting to MinIO bucket '{MINIO_BUCKET_NAME}'. Check keys and policies. ***\n")
         QMessageBox.critical(None, "MinIO Error", f"Access Denied for bucket '{MINIO_BUCKET_NAME}'.")
    else:
        print(f"\n*** CRITICAL: Error connecting to MinIO or bucket '{MINIO_BUCKET_NAME}': {e} ***\n")
        QMessageBox.critical(None, "MinIO Error", f"Could not connect/access bucket '{MINIO_BUCKET_NAME}': {e}")
    s3_client = None # Ensure it's None
except Exception as e:
    print(f"\n*** CRITICAL: Failed to initialize MinIO S3 client: {e} ***\n")
    QMessageBox.critical(None, "MinIO Error", f"Failed to initialize MinIO client: {e}")
    s3_client = None # Ensure it's None


# --- Database Access (Modified for PostgreSQL) ---
@contextmanager
def get_db_connection():
    """Provides a PostgreSQL connection and cursor context."""
    conn = None
    try:
        # print(f"Connecting to PG: {DSN}") # Debug
        conn = psycopg2.connect(DSN)
        # Use RealDictCursor for dictionary-like rows
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield conn, cur # Provide both connection and cursor
    except psycopg2.OperationalError as e:
        print(f"DB Connection Error: {e}")
        QMessageBox.critical(None, "Database Connection Error",
                             f"Could not connect to the database on {DB_HOST}:{DB_PORT}.\n\nError: {e}\n\n"
                             "Check database server, network, firewall, and credentials.")
        raise # Re-raise so calling functions know connection failed
    finally:
        if conn:
            conn.close()

def fetch_requests_from_db():
    """Fetches all requests using psycopg2."""
    # Columns match the table definition in backend/database.py
    sql = ('SELECT id, email, description, status, submitted_at, completed_at, '
           'original_image_path, payment_proof_path, edited_image_path '
           'FROM requests ORDER BY submitted_at DESC')
    try:
        with get_db_connection() as (conn, cur):
            cur.execute(sql)
            # RealDictCursor returns list of dicts directly
            results = cur.fetchall()
            print(f"Fetched {len(results)} rows from DB.")
            return results
    except Exception as e:
        print(f"Error in fetch_requests_from_db: {e}")
        # Avoid showing message box on every refresh error, just log it
        # QMessageBox.critical(None, "Database Error", f"Could not fetch requests: {e}")
        return [] # Return empty list on error

def update_db_request(req_id, status=None, edited_path_relative=None):
    """Updates a request using psycopg2."""
    if req_id is None: return False # Safety check

    try:
        with get_db_connection() as (conn, cur):
            updates = []
            params = []
            if status:
                updates.append("status = %s") # Use %s for psycopg2
                params.append(status)
            if edited_path_relative is not None: # Allow clearing path
                updates.append("edited_image_path = %s")
                params.append(edited_path_relative)
            # Only update completed_at if status is being set to a final state
            if status in ['completed', 'pending_email']:
                 updates.append("completed_at = CURRENT_TIMESTAMP")

            if not updates:
                print(f"No updates specified for request {req_id}")
                return False

            params.append(req_id) # ID for WHERE clause
            sql = f"UPDATE requests SET {', '.join(updates)} WHERE id = %s"
            print(f"Updating DB: {sql} PARAMS: {tuple(params)}") # Debug
            cur.execute(sql, tuple(params))
            conn.commit()
            return cur.rowcount > 0 # Check if rows were affected
    except Exception as e:
        print(f"Error updating request {req_id}: {e}")
        QMessageBox.critical(None, "Database Update Error",
                             f"Could not update request {req_id}: {e}")
        return False


# --- Table Model (Largely Unchanged, Relies on Dict Data) ---
class WaitlistTableModel(QAbstractTableModel):
    # Define column order and headers explicitly
    COLUMNS = ["ID", "Status", "Email", "Submitted", "Completed", "Description"]
    COLUMN_MAP = { # Map internal dict keys to column indices
        "id": 0,
        "status": 1,
        "email": 2,
        "submitted_at": 3,
        "completed_at": 4,
        "description": 5
    }
    DATETIME_FORMAT = "yyyy-MM-dd HH:mm:ss" # Use consistent format

    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self._data = data or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None

        row_data = self._data[index.row()]
        col_index = index.column()

        try:
            if role == Qt.ItemDataRole.DisplayRole:
                # Find the corresponding key in row_data using COLUMN_MAP
                key_to_find = None
                for key, idx in self.COLUMN_MAP.items():
                    if idx == col_index:
                        key_to_find = key
                        break

                if key_to_find:
                    value = row_data.get(key_to_find)
                    if value is None:
                         return "" # Represent None as empty string
                    # Format datetime objects correctly
                    if isinstance(value, (datetime.datetime, datetime.date)):
                        qdt = QDateTime(value)
                        # Handle timezones if present in PG data (TIMESTAMPTZ)
                        # This might need adjustment based on how PG returns TZ info via psycopg2
                        # For simplicity, we display in local time or UTC depending on QDateTime default
                        return qdt.toString(self.DATETIME_FORMAT)
                    return str(value) # Default string conversion
                else:
                    return "" # Column index out of map range (shouldn't happen)

            elif role == Qt.ItemDataRole.UserRole: # Return the full row dict
                return row_data

        except Exception as e:
             print(f"Error in model data() [Row:{index.row()}, Col:{col_index}]: {e}")
             return None # Indicate error

        return None # Default return

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if section < len(self.COLUMNS):
                return self.COLUMNS[section]
        return super().headerData(section, orientation, role)

    def refreshData(self):
        print("Model: Refreshing data...")
        self.beginResetModel()
        self._data = fetch_requests_from_db() # Fetch directly from PG
        print(f"Model: Fetched {len(self._data)} rows.")
        self.endResetModel()

    def getRowData(self, row_index):
         if 0 <= row_index < len(self._data):
            return self._data[row_index]
         return None

# --- Filter Proxy Model (Unchanged) ---
class RequestFilterProxyModel(QSortFilterProxyModel):
    # (Keep the existing filter proxy model code)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1) # Search across all columns

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.filterRegularExpression().pattern():
            return True # No filter applied

        model = self.sourceModel()
        for col in range(model.columnCount()):
            index = model.index(source_row, col, source_parent)
            data = model.data(index, Qt.ItemDataRole.DisplayRole)
            if data and self.filterRegularExpression().match(data).hasMatch():
                return True
        return False

    def lessThan(self, left, right):
        # Custom sorting for date/time columns if needed
        left_data = self.sourceModel().data(left)
        right_data = self.sourceModel().data(right)
        col = left.column()

        # Use the COLUMN_MAP from the source model for checking
        source_model = self.sourceModel()
        is_date_col = False
        if col == source_model.COLUMN_MAP.get("submitted_at") or \
           col == source_model.COLUMN_MAP.get("completed_at"):
             is_date_col = True

        if is_date_col:
            # Attempt to parse strings back to QDateTime for comparison
            # Ensure data is string before parsing
            left_dt = QDateTime.fromString(str(left_data), source_model.DATETIME_FORMAT)
            right_dt = QDateTime.fromString(str(right_data), source_model.DATETIME_FORMAT)

            if left_dt.isValid() and right_dt.isValid():
                return left_dt < right_dt
            elif left_dt.isValid(): # Valid dates come before invalid/empty ones
                return True
            elif right_dt.isValid(): # Invalid/empty ones come after valid ones
                return False
            else: # Both invalid or empty, fallback to string comparison
                 return str(left_data) < str(right_data)

        # Default comparison for other columns using base class
        return super().lessThan(left, right)

# --- Main UI Window ---
class WaitlistManager(QWidget):
    def __init__(self):
        super().__init__()
        self._current_request_id = None
        self._current_request_data = None
        self.copy_email_button = None
        self.send_email_button = None
        # Check if S3 client is available before starting UI fully?
        if s3_client is None:
             QMessageBox.critical(self, "MinIO Client Error",
                                  "MinIO S3 client could not be initialized. Image previews and uploads will not work.")
             # Optionally disable features or exit
             # sys.exit(1) # Exit if MinIO is critical

        self.init_ui()
        self.setup_model()
        self.refresh_data() # Load initial data

    def init_ui(self):
        # (Keep the general UI layout from previous version)
        # ... (Same layout code as before, including labels, buttons, tableview) ...
        main_layout = QVBoxLayout(self)

        # Top Controls (Filter + Refresh)
        controls_layout = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter requests (ID, email, status, etc.)...")
        self.refresh_button = QPushButton("Refresh List")
        controls_layout.addWidget(QLabel("Filter:"))
        controls_layout.addWidget(self.filter_edit)
        controls_layout.addWidget(self.refresh_button)
        main_layout.addLayout(controls_layout)

        # Main Area (Table on Left, Details on Right)
        main_area_layout = QHBoxLayout()

        # Left: Table View
        self.table_view = QTableView()
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.setSortingEnabled(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_area_layout.addWidget(self.table_view, 2) # Give table more space

        # Right: Details Panel
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.details_header = QLabel("Select a request to view details")
        font = self.details_header.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        self.details_header.setFont(font)
        details_layout.addWidget(self.details_header)

        # Using QGridLayout for better label alignment
        details_grid = QGridLayout()
        details_grid.addWidget(QLabel("<b>ID:</b>"), 0, 0)
        self.id_label = QLabel("-")
        self.id_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_grid.addWidget(self.id_label, 0, 1, 1, 2) # Span 2 cols

        details_grid.addWidget(QLabel("<b>Email:</b>"), 1, 0)
        self.email_label = QLabel("-")
        self.email_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_email_button = QPushButton("Copy")
        self.copy_email_button.clicked.connect(self.copy_email)
        details_grid.addWidget(self.email_label, 1, 1)
        details_grid.addWidget(self.copy_email_button, 1, 2)


        details_grid.addWidget(QLabel("<b>Status:</b>"), 2, 0)
        self.status_label = QLabel("-")
        details_grid.addWidget(self.status_label, 2, 1, 1, 2) # Span 2 cols

        details_grid.addWidget(QLabel("<b>Description:</b>"), 3, 0, Qt.AlignmentFlag.AlignTop)
        self.description_text = QTextEdit()
        self.description_text.setReadOnly(True)
        self.description_text.setMaximumHeight(80) # Limit height
        details_grid.addWidget(self.description_text, 3, 1, 1, 2) # Span 2 columns

        details_layout.addLayout(details_grid)

        # Image Previews and Actions
        image_layout = QHBoxLayout()
        image_preview_size = 150

        orig_vbox = QVBoxLayout()
        self.original_image_label = QLabel("Original Image")
        self.original_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_image_label.setFixedSize(image_preview_size, image_preview_size)
        self.original_image_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
        orig_button_layout = QHBoxLayout()
        self.view_orig_button = QPushButton("View")
        self.copy_orig_path_button = QPushButton("Copy Key") # Changed label
        orig_button_layout.addWidget(self.view_orig_button)
        orig_button_layout.addWidget(self.copy_orig_path_button)
        orig_vbox.addWidget(self.original_image_label)
        orig_vbox.addLayout(orig_button_layout)
        image_layout.addLayout(orig_vbox)

        proof_vbox = QVBoxLayout()
        self.proof_image_label = QLabel("Payment Proof")
        self.proof_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.proof_image_label.setFixedSize(image_preview_size, image_preview_size)
        self.proof_image_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
        proof_button_layout = QHBoxLayout()
        self.view_proof_button = QPushButton("View")
        # self.copy_proof_path_button = QPushButton("Copy Key") # Optional
        proof_button_layout.addWidget(self.view_proof_button)
        # proof_button_layout.addWidget(self.copy_proof_path_button)
        proof_vbox.addWidget(self.proof_image_label)
        proof_vbox.addLayout(proof_button_layout)
        image_layout.addLayout(proof_vbox)

        edited_vbox = QVBoxLayout()
        self.edited_image_label = QLabel("Edited Image")
        self.edited_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edited_image_label.setFixedSize(image_preview_size, image_preview_size)
        self.edited_image_label.setStyleSheet("border: 1px solid lightblue; background-color: #f0f8ff;")
        edited_button_layout = QHBoxLayout()
        self.upload_edited_button = QPushButton("Upload New")
        self.view_edited_button = QPushButton("View")
        # self.copy_edited_path_button = QPushButton("Copy Key") # Optional
        edited_button_layout.addWidget(self.upload_edited_button)
        edited_button_layout.addWidget(self.view_edited_button)
        # edited_button_layout.addWidget(self.copy_edited_path_button)
        edited_vbox.addWidget(self.edited_image_label)
        edited_vbox.addLayout(edited_button_layout)
        image_layout.addLayout(edited_vbox)


        details_layout.addLayout(image_layout)
        details_layout.addStretch() # Push button to bottom

        # Action Buttons at the bottom of details panel
        action_button_layout = QHBoxLayout()

        self.mark_complete_button = QPushButton("Mark Ready for Email") # Renamed
        self.mark_complete_button.setStyleSheet("background-color: lightgreen;")
        action_button_layout.addWidget(self.mark_complete_button)

        self.send_email_button = QPushButton("Send Completion Email")
        self.send_email_button.setStyleSheet("background-color: lightblue;")
        action_button_layout.addWidget(self.send_email_button)

        details_layout.addLayout(action_button_layout)

        details_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        main_area_layout.addWidget(details_widget, 1) # Give details less space initially

        main_layout.addLayout(main_area_layout)

        # Window properties
        self.setWindowTitle("Image Request Manager (Direct DB/MinIO)")
        self.setGeometry(100, 100, 1200, 700)

        # Connect signals
        self.refresh_button.clicked.connect(self.refresh_data)
        self.filter_edit.textChanged.connect(self.filter_requests)

        self.view_orig_button.clicked.connect(lambda: self.view_image('original'))
        self.copy_orig_path_button.clicked.connect(lambda: self.copy_image_path('original'))
        self.view_proof_button.clicked.connect(lambda: self.view_image('proof'))
        # self.copy_proof_path_button.clicked.connect(lambda: self.copy_image_path('proof')) # Optional
        self.upload_edited_button.clicked.connect(self.upload_edited_image)
        self.view_edited_button.clicked.connect(lambda: self.view_image('edited'))
        # self.copy_edited_path_button.clicked.connect(lambda: self.copy_image_path('edited')) # Optional
        self.mark_complete_button.clicked.connect(self.mark_ready_for_email) # Renamed handler
        self.send_email_button.clicked.connect(self.send_completion_email) # Stays the same (uses API)

        # Disable buttons initially
        self.disable_detail_buttons()

    def setup_model(self):
        # (Setup model logic remains the same as previous version)
        self.table_model = WaitlistTableModel()
        self.proxy_model = RequestFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)

        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["id"], QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["status"], QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["email"], QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["submitted_at"], QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["completed_at"], QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["description"], QHeaderView.ResizeMode.Stretch)
        self.table_view.setColumnWidth(WaitlistTableModel.COLUMN_MAP["email"], 180)

        self.table_view.selectionModel().selectionChanged.connect(self.on_selection_changed)
        self.table_view.doubleClicked.connect(self.on_double_click)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_table_context_menu)

    def refresh_data(self):
        """Reloads data from the database into the table."""
        print("UI: Refresh triggered.")
        current_selection_id = self._current_request_id # Store selection
        self.table_model.refreshData()
        self.try_reselect_row(current_selection_id) # Try to reselect after refresh

    def filter_requests(self, text):
        # (Remains the same)
        search = QRegularExpression(text, QRegularExpression.PatternOption.CaseInsensitiveOption | QRegularExpression.PatternOption.UseUnicodePropertiesOption)
        self.proxy_model.setFilterRegularExpression(search)

    def on_selection_changed(self, selected, deselected):
        # (Remains largely the same, just triggers new load_all_previews)
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            self.clear_details()
            self.disable_detail_buttons()
            return
        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        if not source_index.isValid(): return
        row_data = self.table_model.getRowData(source_index.row())
        if row_data:
            print(f"UI: Selection changed to ID: {row_data.get('id')}")
            self._current_request_id = row_data.get('id')
            self._current_request_data = row_data
            self.update_details_view(row_data) # Update text labels
            self.load_all_previews(row_data)   # Load image previews from MinIO
            self.enable_detail_buttons(row_data) # Update button states
        else:
            print("UI: Selection changed, but no row data found.")
            self.clear_details()
            self.disable_detail_buttons()

    def on_double_click(self, index):
        # (Remains the same)
        if self._current_request_id:
            self.view_image('original')

    def show_table_context_menu(self, position):
        # (Remains the same, logic relies on _current_request_data which is set)
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes: return
        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        row_data = self.table_model.getRowData(source_index.row())
        if not row_data: return

        menu = QMenu()
        # Add actions with checks based on row_data
        if row_data.get('original_image_path'):
             view_orig_action = menu.addAction("View Original Image")
        else: view_orig_action = None
        # ... (Add other view/copy actions similarly) ...
        if row_data.get('email'):
             copy_email_action = menu.addAction("Copy Email Address")
        else: copy_email_action = None
        copy_id_action = menu.addAction("Copy Request ID")
        # ... (Add mark ready/send email actions with status checks) ...
        action = menu.exec(self.table_view.viewport().mapToGlobal(position))
        # Handle selected action
        if action == view_orig_action: self.view_image('original')
        elif action == copy_email_action: self.copy_email()
        elif action == copy_id_action: self.copy_id()
        # ... handle other actions ...

    def update_details_view(self, data):
        """Populates the text details panel with data from the selected row."""
        # (Remains the same - only updates text)
        self.details_header.setText(f"Details for Request {data.get('id', '')[:8]}...")
        self.id_label.setText(data.get('id', 'N/A'))
        self.email_label.setText(data.get('email', 'N/A'))
        self.status_label.setText(data.get('status', 'N/A').capitalize())
        self.description_text.setText(data.get('description', ''))
        # Image loading is handled by load_all_previews

    # --- NEW: Function to trigger loading all previews from MinIO ---
    def load_all_previews(self, data):
        """Initiates loading for all image previews from MinIO."""
        if s3_client is None:
            print("UI: Cannot load previews, S3 client not available.")
            self.original_image_label.setText("(MinIO Error)")
            self.proof_image_label.setText("(MinIO Error)")
            self.edited_image_label.setText("(MinIO Error)")
            return

        print(f"UI: Loading previews for ID: {data.get('id')}")
        # Direct loading (freezes UI) - Add threading later if needed
        self.load_preview_image(self.original_image_label, data.get('original_image_path'))
        self.load_preview_image(self.proof_image_label, data.get('payment_proof_path'))
        self.load_preview_image(self.edited_image_label, data.get('edited_image_path'))

    # --- MODIFIED: Load preview image directly from MinIO ---
    def load_preview_image(self, label_widget, object_key):
        """Loads an image preview by fetching object from MinIO."""
        label_widget.setText("(Loading...)")
        label_widget.setPixmap(QPixmap())
        label_widget.setToolTip("")

        if not object_key:
            label_widget.setText("(No image)")
            return

        if s3_client is None:
             label_widget.setText("(MinIO N/A)")
             return

        print(f"UI: Fetching preview from MinIO: Bucket='{MINIO_BUCKET_NAME}', Key='{object_key}'")
        label_widget.setToolTip(f"Bucket: {MINIO_BUCKET_NAME}\nKey: {object_key}")

        try:
            # Get the object data from MinIO
            response = s3_client.get_object(Bucket=MINIO_BUCKET_NAME, Key=object_key)
            image_data = response['Body'].read()

            if not image_data:
                 label_widget.setText("(Empty Object)")
                 print(f"Warning: Received empty object data for {object_key}")
                 return

            pixmap = QPixmap()
            if pixmap.loadFromData(image_data):
                 # Scale pixmap to fit the label
                 scaled_pixmap = pixmap.scaled(label_widget.size(),
                                            Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
                 label_widget.setPixmap(scaled_pixmap)
            else:
                 label_widget.setText("(Invalid Img Data)")
                 print(f"Warning: Could not load image data from MinIO object {object_key} into QPixmap.")

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'NoSuchKey':
                 label_widget.setText("(Not Found)")
                 print(f"Warning: MinIO object key not found: {object_key}")
                 label_widget.setToolTip(f"Bucket: {MINIO_BUCKET_NAME}\nKey: {object_key}\nError: Not Found")
            elif error_code == 'AccessDenied':
                 label_widget.setText("(Access Denied)")
                 print(f"Warning: Access Denied fetching MinIO object: {object_key}")
                 label_widget.setToolTip(f"Bucket: {MINIO_BUCKET_NAME}\nKey: {object_key}\nError: Access Denied")
            else:
                 label_widget.setText("(MinIO Error)")
                 print(f"Warning: MinIO ClientError fetching object {object_key}: {e}")
                 label_widget.setToolTip(f"Bucket: {MINIO_BUCKET_NAME}\nKey: {object_key}\nError: {error_code}")
        except Exception as e:
             label_widget.setText("(Load Error)")
             print(f"Error loading image {object_key} from MinIO: {e}")
             label_widget.setToolTip(f"Bucket: {MINIO_BUCKET_NAME}\nKey: {object_key}\nError: An unexpected error occurred.")


    def clear_details(self):
        # (Remains the same)
        self._current_request_id = None
        self._current_request_data = None
        self.details_header.setText("Select a request to view details")
        self.id_label.setText("-")
        self.email_label.setText("-")
        self.status_label.setText("-")
        self.description_text.clear()
        self.original_image_label.setText("Original Image")
        self.original_image_label.setPixmap(QPixmap())
        self.original_image_label.setToolTip("")
        self.proof_image_label.setText("Payment Proof")
        self.proof_image_label.setPixmap(QPixmap())
        self.proof_image_label.setToolTip("")
        self.edited_image_label.setText("Edited Image")
        self.edited_image_label.setPixmap(QPixmap())
        self.edited_image_label.setToolTip("")
        self.disable_detail_buttons()


    def disable_detail_buttons(self):
        # (Remains the same, maybe disable based on s3_client too)
        has_s3 = s3_client is not None
        self.view_orig_button.setEnabled(False)
        self.copy_orig_path_button.setEnabled(False) # Copies key now
        self.view_proof_button.setEnabled(False)
        self.upload_edited_button.setEnabled(False)
        self.view_edited_button.setEnabled(False)
        self.mark_complete_button.setEnabled(False)
        self.copy_email_button.setEnabled(False)
        self.send_email_button.setEnabled(False)

        # Disable image actions if s3 client failed
        if not has_s3:
             self.view_orig_button.setEnabled(False)
             self.view_proof_button.setEnabled(False)
             self.upload_edited_button.setEnabled(False)
             self.view_edited_button.setEnabled(False)


    def enable_detail_buttons(self, data):
        # (Remains largely the same, check s3_client)
        if s3_client is None: # If no S3 client, most buttons remain disabled
            self.disable_detail_buttons()
            # Maybe still allow copying ID/Email?
            self.copy_email_button.setEnabled(bool(data.get('email')))
            return

        status = data.get('status', 'pending')
        has_orig = bool(data.get('original_image_path'))
        has_proof = bool(data.get('payment_proof_path'))
        has_edited = bool(data.get('edited_image_path'))
        has_email = bool(data.get('email'))

        can_upload = True # Allow upload/overwrite for testing
        can_mark_ready = status not in ['pending_email', 'completed', 'email_sent'] and has_edited
        can_send_email = status == 'pending_email' and has_email and has_edited

        self.view_orig_button.setEnabled(has_orig)
        self.copy_orig_path_button.setEnabled(has_orig) # Copies key
        self.view_proof_button.setEnabled(has_proof)
        self.upload_edited_button.setEnabled(can_upload)
        self.view_edited_button.setEnabled(has_edited)
        self.mark_complete_button.setEnabled(can_mark_ready)
        self.copy_email_button.setEnabled(has_email)
        self.send_email_button.setEnabled(can_send_email)


    def get_minio_object_key(self, image_type):
        """Gets the MinIO object key for the selected request's image."""
        if not self._current_request_data: return None
        key_map = {
            'original': 'original_image_path',
            'proof': 'payment_proof_path',
            'edited': 'edited_image_path'
        }
        return self._current_request_data.get(key_map.get(image_type))

    # --- MODIFIED: view_image uses pre-signed URL from MinIO ---
    def view_image(self, image_type):
        """Generates a pre-signed URL and opens it in the browser."""
        if s3_client is None:
             QMessageBox.warning(self, "MinIO Error", "MinIO client not available.")
             return

        object_key = self.get_minio_object_key(image_type)

        if object_key:
            try:
                # Generate pre-signed URL (expires in 1 hour, adjust as needed)
                url_expiration = 3600
                presigned_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': MINIO_BUCKET_NAME, 'Key': object_key},
                    ExpiresIn=url_expiration
                )
                print(f"Generated pre-signed URL for {object_key}: {presigned_url}")

                # Open the URL using QDesktopServices
                if not QDesktopServices.openUrl(QUrl(presigned_url)):
                    QMessageBox.warning(self, "Open URL Failed", f"Could not open URL in browser:\n{presigned_url}")

            except ClientError as e:
                 QMessageBox.critical(self, "MinIO Error", f"Could not generate URL for {object_key}: {e}")
                 print(f"Error generating pre-signed URL for {object_key}: {e}")
            except Exception as e:
                 QMessageBox.critical(self, "Error", f"An unexpected error occurred generating URL: {e}")
                 print(f"Unexpected error generating URL for {object_key}: {e}")

        elif self._current_request_id:
             QMessageBox.information(self, "No Image", f"No {image_type} image path (object key) found for this request.")


    def copy_to_clipboard(self, text):
        # (Remains the same)
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            print(f"Copied to clipboard: {text[:50]}...")
        else:
             print("Nothing to copy.")

    def copy_email(self):
        # (Remains the same)
        if self._current_request_data:
            self.copy_to_clipboard(self._current_request_data.get('email'))

    def copy_id(self):
        # (Remains the same)
         if self._current_request_data:
            self.copy_to_clipboard(self._current_request_data.get('id'))

    # --- MODIFIED: copy_image_path copies the MinIO object key ---
    def copy_image_path(self, image_type):
        """Copies the MinIO object key to the clipboard."""
        object_key = self.get_minio_object_key(image_type)
        self.copy_to_clipboard(object_key)


    # --- MODIFIED: Upload edited image directly to MinIO ---
    def upload_edited_image(self):
        """Opens dialog, uploads selected file to MinIO, updates DB."""
        if not self._current_request_id:
            QMessageBox.warning(self, "No Request Selected", "Please select a request first.")
            return
        if s3_client is None:
             QMessageBox.warning(self, "MinIO Error", "MinIO client not available for upload.")
             return

        fileName, _ = QFileDialog.getOpenFileName(self, "Select Edited Image File", "",
                                                  "Image Files (*.png *.jpg *.jpeg *.gif *.webp)")

        if fileName:
            try:
                # Determine the extension
                source_ext = os.path.splitext(fileName)[1].lower()
                if not source_ext: source_ext = ".png" # Default

                # Construct the MinIO object key (using posixpath for consistency)
                target_filename_base = f"{self._current_request_id}_edited{source_ext}"
                object_key = posixpath.join('edited', target_filename_base) # e.g., "edited/uuid_edited.png"

                print(f"Uploading {fileName} to MinIO: Bucket='{MINIO_BUCKET_NAME}', Key='{object_key}'")

                # Upload the file to MinIO
                # You might want to add ExtraArgs for ContentType if needed
                # content_type = mimetypes.guess_type(fileName)[0] or 'application/octet-stream'
                s3_client.upload_file(
                    fileName,
                    MINIO_BUCKET_NAME,
                    object_key
                    # ExtraArgs={'ContentType': content_type}
                 )
                print("MinIO upload successful.")

                # Update the database with the object key
                if update_db_request(self._current_request_id, edited_path_relative=object_key):
                    QMessageBox.information(self, "Upload Successful",
                                            f"Image uploaded to MinIO and database updated.\nKey: {object_key}")
                    self.try_reselect_row(self._current_request_id) # Refresh UI
                else:
                    QMessageBox.warning(self, "Database Error",
                                        "Image uploaded to MinIO, but failed to update database path.")
                    # Consider deleting the uploaded object if DB update fails?
                    # try:
                    #     print(f"Attempting to delete {object_key} due to DB error...")
                    #     s3_client.delete_object(Bucket=MINIO_BUCKET_NAME, Key=object_key)
                    # except Exception as del_e:
                    #     print(f"Failed to delete uploaded object {object_key}: {del_e}")

            except ClientError as e:
                QMessageBox.critical(self, "MinIO Upload Failed", f"Could not upload to MinIO: {e}")
                print(f"Error uploading to MinIO: {e}")
            except Exception as e:
                QMessageBox.critical(self, "Upload Failed", f"An unexpected error occurred: {e}")
                print(f"Error during edited image upload process: {e}")


    # --- RENAMED: mark_ready_for_email (Logic remains DB focused) ---
    def mark_ready_for_email(self):
        # (Logic remains the same as previous version - updates DB status)
        if not self._current_request_id or not self._current_request_data:
            QMessageBox.warning(self, "No Request Selected", "Please select a request first.")
            return
        edited_path = self._current_request_data.get('edited_image_path')
        if not edited_path:
            QMessageBox.warning(self, "Missing Edited Image Path", "Cannot mark as ready without an edited image path in the database.")
            return
        current_status = self._current_request_data.get('status')
        if current_status in ['pending_email', 'completed', 'email_sent']:
            QMessageBox.information(self, "Already Processed", f"This request status is already '{current_status}'.")
            return
        recipient_email = self._current_request_data.get('email', 'N/A')
        reply = QMessageBox.question(self, 'Confirm Ready for Email',
                                     f"Mark request {self._current_request_id[:8]}... as ready to send email?\nEmail: {recipient_email}\nEdited Path: {edited_path}\n(Status will be set to 'pending_email')",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if update_db_request(self._current_request_id, status='pending_email'):
                QMessageBox.information(self, "Status Updated", "Request status set to 'pending_email'. You can now send the completion email.")
                self.try_reselect_row(self._current_request_id)
            else:
                QMessageBox.warning(self, "Database Error", "Failed to update request status.")


    # --- send_completion_email (Unchanged - Still uses Backend API) ---
    def send_completion_email(self):
        """Triggers the backend endpoint to send the completion email."""
        if not self._current_request_id or not self._current_request_data:
             QMessageBox.warning(self, "No Request Selected", "Please select a request first.")
             return
        status = self._current_request_data.get('status')
        recipient_email = self._current_request_data.get('email')
        edited_path = self._current_request_data.get('edited_image_path')

        if status != 'pending_email':
             QMessageBox.warning(self, "Invalid Status", f"Request status is '{status}', not 'pending_email'. Cannot send email.")
             return
        if not recipient_email:
            QMessageBox.warning(self, "Missing Email", "Cannot send: Recipient email address is missing.")
            return
        if not edited_path:
             QMessageBox.warning(self, "Missing Edited Image Path", "Cannot send: Edited image path is missing.")
             return

        reply = QMessageBox.question(self, 'Confirm Email Send',
                                     f"Trigger backend to send image ({edited_path}) to:\n{recipient_email}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No: return

        self.send_email_button.setEnabled(False); self.send_email_button.setText("Sending...")
        QApplication.processEvents()
        request_id = self._current_request_id
        url = f"{API_BASE_URL}/send_completion_email/{request_id}" # Use correct API_BASE_URL
        print(f"UI: Calling API to send email: POST {url}")
        try:
            response = requests.post(url, timeout=45)
            if response.status_code == 200:
                QMessageBox.information(self, "Email Send Triggered", response.json().get("message", "Backend acknowledged email request."))
                self.try_reselect_row(request_id)
            else:
                try: error_msg = response.json().get('error', f'Status: {response.status_code}')
                except requests.exceptions.JSONDecodeError: error_msg = response.text or f'Status: {response.status_code}'
                QMessageBox.critical(self, "Email Send Failed", f"Backend Error: {error_msg}")
                print(f"Error from backend API ({url}): {response.status_code} - {error_msg}")
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "API Connection Error", f"Could not trigger email send:\n{e}")
            print(f"Error calling backend API ({url}): {e}")
        finally:
            self.send_email_button.setText("Send Completion Email")
            # Re-enable based on current status (might need a quick re-fetch or rely on refresh)
            selection_model = self.table_view.selectionModel()
            if selection_model and selection_model.hasSelection():
                current_proxy_index = selection_model.selectedRows()[0]
                current_source_index = self.proxy_model.mapToSource(current_proxy_index)
                current_data = self.table_model.getRowData(current_source_index.row())
                if current_data: self.enable_detail_buttons(current_data)
                else: self.disable_detail_buttons()
            else: self.disable_detail_buttons()


    # --- HELPER: Refresh data and try to reselect row by ID ---
    def try_reselect_row(self, reselect_id):
        """Attempts to find and select a row by ID after a data refresh."""
        if reselect_id is None:
             self.clear_details() # If no ID to reselect, just clear details
             return

        new_proxy_index = QModelIndex() # Invalid index initially
        for row in range(self.proxy_model.rowCount()):
            check_proxy_index = self.proxy_model.index(row, 0)
            check_source_index = self.proxy_model.mapToSource(check_proxy_index)
            row_data = self.table_model.getRowData(check_source_index.row())
            if row_data and row_data.get('id') == reselect_id:
                new_proxy_index = check_proxy_index # Found it
                break

        if new_proxy_index.isValid():
            print(f"UI: Reselecting row {new_proxy_index.row()} for ID {reselect_id}")
            self.table_view.selectRow(new_proxy_index.row())
            self.table_view.scrollTo(new_proxy_index, QAbstractItemView.ScrollHint.EnsureVisible)
        else:
            print(f"UI: Could not find ID {reselect_id} after refresh, clearing details.")
            self.clear_details() # If ID not found, clear details


# --- Run Application ---
if __name__ == "__main__":
    # Perform checks before starting UI
    db_ok = False
    try:
        with get_db_connection() as (conn, cur):
            cur.execute("SELECT 1") # Test DB connection
        db_ok = True
        print("Database connection successful.")
    except Exception as e:
         # Error message already shown by get_db_connection
         print("Exiting due to database connection failure.")
         sys.exit(1)

    if s3_client is None:
         print("Exiting due to MinIO S3 client initialization failure.")
         sys.exit(1)

    app = QApplication(sys.argv)
    manager = WaitlistManager()
    manager.show()
    sys.exit(app.exec())