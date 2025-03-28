# manager_ui.py

import sys
import os
import posixpath
import shutil
import requests
import datetime
from contextlib import contextmanager

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

import psycopg2
import psycopg2.extras

# --- Configuration ---
# Local folder to store copies of uploaded edited images.
EDITED_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'uploads', 'edited'))

# API endpoint base URL (adjust as needed)
API_BASE_URL = 'http://192.168.0.112'

# --- Database Connection Details ---
# In a production app these values should be securely loaded (e.g., from environment variables)
DB_NAME = "image_trend_db"       # Match POSTGRES_DB in your environment
DB_USER = "trend_user"           # Match POSTGRES_USER
DB_PASSWORD = "a_very_secret_pg_password"  # Match POSTGRES_PASSWORD
DB_HOST = "192.168.0.112"         # IP address of your PostgreSQL server
DB_PORT = "5432"                # Port exposed by docker-compose or your PostgreSQL server
DSN = f"dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}' host='{DB_HOST}' port='{DB_PORT}'"

# --- Database Access ---
@contextmanager
def get_db_connection():
    """Provides a PostgreSQL connection and cursor context."""
    conn = None
    try:
        conn = psycopg2.connect(DSN)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield conn, cur
    except psycopg2.OperationalError as e:
        print(f"DB Connection Error: {e}")
        QMessageBox.critical(None, "Database Connection Error",
                             f"Could not connect to the database on {DB_HOST}:{DB_PORT}.\n\nError: {e}\n\n"
                             "Check database server, network, firewall, and credentials.")
        raise
    finally:
        if conn:
            conn.close()

def fetch_requests_from_db():
    """Fetches all requests using psycopg2."""
    sql = ('SELECT id, email, description, status, submitted_at, completed_at, '
           'original_image_path, payment_proof_path, edited_image_path '
           'FROM requests ORDER BY submitted_at DESC')
    try:
        with get_db_connection() as (conn, cur):
            cur.execute(sql)
            return cur.fetchall()
    except Exception as e:
        print(f"Error in fetch_requests_from_db: {e}")
        return []

def update_db_request(req_id, status=None, edited_path_relative=None):
    """Updates a request using psycopg2."""
    try:
        with get_db_connection() as (conn, cur):
            updates = []
            params = []
            if status:
                updates.append("status = %s")
                params.append(status)
            if edited_path_relative is not None:
                updates.append("edited_image_path = %s")
                params.append(edited_path_relative)
            if status == 'completed':
                updates.append("completed_at = CURRENT_TIMESTAMP")
            if not updates:
                return False
            params.append(req_id)
            sql = f"UPDATE requests SET {', '.join(updates)} WHERE id = %s"
            cur.execute(sql, tuple(params))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        print(f"Error updating request {req_id}: {e}")
        QMessageBox.critical(None, "Database Update Error",
                             f"Could not update request {req_id}: {e}")
        return False

# --- Table Model ---
class WaitlistTableModel(QAbstractTableModel):
    COLUMNS = ["ID", "Status", "Email", "Submitted", "Completed", "Description"]
    COLUMN_MAP = {
        "id": 0,
        "status": 1,
        "email": 2,
        "submitted_at": 3,
        "completed_at": 4,
        "description": 5
    }
    DATETIME_FORMAT = "yyyy-MM-dd HH:mm:ss"

    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self._data = data or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row_data = self._data[index.row()]
        col_index = index.column()

        try:
            if role == Qt.ItemDataRole.DisplayRole:
                key_to_find = None
                for key, idx in self.COLUMN_MAP.items():
                    if idx == col_index:
                        key_to_find = key
                        break
                if key_to_find:
                    value = row_data.get(key_to_find)
                    if value is None:
                        return ""
                    if isinstance(value, (datetime.datetime, datetime.date)):
                        qdt = QDateTime(value)
                        return qdt.toString(self.DATETIME_FORMAT)
                    return str(value)
                else:
                    return ""
            elif role == Qt.ItemDataRole.UserRole:
                return row_data
        except Exception as e:
            print(f"Error in model data function: Row {index.row()}, Col {col_index}, Error: {e}")
            return None
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return super().headerData(section, orientation, role)

    def refreshData(self):
        self.beginResetModel()
        self._data = fetch_requests_from_db()
        self.endResetModel()

    def getRowData(self, row_index):
        if 0 <= row_index < len(self._data):
            return self._data[row_index]
        return None

# --- Filter Proxy Model ---
class RequestFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.filterRegularExpression().pattern():
            return True
        model = self.sourceModel()
        for col in range(model.columnCount()):
            index = model.index(source_row, col, source_parent)
            data = model.data(index, Qt.ItemDataRole.DisplayRole)
            if data and self.filterRegularExpression().match(data).hasMatch():
                return True
        return False

    def lessThan(self, left, right):
        left_data = self.sourceModel().data(left)
        right_data = self.sourceModel().data(right)
        col = left.column()
        if col in [WaitlistTableModel.COLUMN_MAP["submitted_at"], WaitlistTableModel.COLUMN_MAP["completed_at"]]:
            left_dt = QDateTime.fromString(left_data, WaitlistTableModel.DATETIME_FORMAT)
            right_dt = QDateTime.fromString(right_data, WaitlistTableModel.DATETIME_FORMAT)
            if left_dt.isValid() and right_dt.isValid():
                return left_dt < right_dt
            elif left_dt.isValid():
                return True
            elif right_dt.isValid():
                return False
            return str(left_data) < str(right_data)
        return super().lessThan(left, right)

# --- Main UI Window ---
class WaitlistManager(QWidget):
    def __init__(self):
        super().__init__()
        self._current_request_id = None
        self._current_request_data = None
        self.copy_email_button = None
        self.init_ui()
        self.setup_model()
        self.refresh_data()

    def init_ui(self):
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
        main_area_layout.addWidget(self.table_view, 2)

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

        # Details Grid
        details_grid = QGridLayout()
        details_grid.addWidget(QLabel("<b>ID:</b>"), 0, 0)
        self.id_label = QLabel("-")
        self.id_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_grid.addWidget(self.id_label, 0, 1)

        details_grid.addWidget(QLabel("<b>Email:</b>"), 1, 0)
        self.email_label = QLabel("-")
        self.email_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_email_button = QPushButton("Copy")
        self.copy_email_button.clicked.connect(self.copy_email)
        details_grid.addWidget(self.email_label, 1, 1)
        details_grid.addWidget(self.copy_email_button, 1, 2)

        details_grid.addWidget(QLabel("<b>Status:</b>"), 2, 0)
        self.status_label = QLabel("-")
        details_grid.addWidget(self.status_label, 2, 1)

        details_grid.addWidget(QLabel("<b>Description:</b>"), 3, 0, Qt.AlignmentFlag.AlignTop)
        self.description_text = QTextEdit()
        self.description_text.setReadOnly(True)
        self.description_text.setMaximumHeight(80)
        details_grid.addWidget(self.description_text, 3, 1, 1, 2)

        details_layout.addLayout(details_grid)

        # Image Previews and Actions
        image_layout = QHBoxLayout()
        self.original_image_label = QLabel("Original Image")
        self.original_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_image_label.setFixedSize(150, 150)
        self.original_image_label.setStyleSheet("border: 1px solid gray;")
        self.view_orig_button = QPushButton("View Original")
        self.copy_orig_path_button = QPushButton("Copy Path")

        self.proof_image_label = QLabel("Payment Proof")
        self.proof_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.proof_image_label.setFixedSize(150, 150)
        self.proof_image_label.setStyleSheet("border: 1px solid gray;")
        self.view_proof_button = QPushButton("View Proof")

        self.edited_image_label = QLabel("Edited Image")
        self.edited_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edited_image_label.setFixedSize(150, 150)
        self.edited_image_label.setStyleSheet("border: 1px solid lightblue;")
        self.upload_edited_button = QPushButton("Upload Edited")
        self.view_edited_button = QPushButton("View Edited")

        orig_vbox = QVBoxLayout()
        orig_vbox.addWidget(self.original_image_label)
        orig_vbox.addWidget(self.view_orig_button)
        orig_vbox.addWidget(self.copy_orig_path_button)
        image_layout.addLayout(orig_vbox)

        proof_vbox = QVBoxLayout()
        proof_vbox.addWidget(self.proof_image_label)
        proof_vbox.addWidget(self.view_proof_button)
        image_layout.addLayout(proof_vbox)

        edited_vbox = QVBoxLayout()
        edited_vbox.addWidget(self.edited_image_label)
        edited_vbox.addWidget(self.upload_edited_button)
        edited_vbox.addWidget(self.view_edited_button)
        image_layout.addLayout(edited_vbox)

        details_layout.addLayout(image_layout)
        details_layout.addStretch()

        # Action Buttons
        action_button_layout = QHBoxLayout()
        self.mark_complete_button = QPushButton("Mark as Completed")
        self.mark_complete_button.setStyleSheet("background-color: lightgreen;")
        action_button_layout.addWidget(self.mark_complete_button)

        self.send_email_button = QPushButton("Send Completion Email")
        self.send_email_button.setStyleSheet("background-color: lightblue;")
        action_button_layout.addWidget(self.send_email_button)

        details_layout.addLayout(action_button_layout)

        details_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        main_area_layout.addWidget(details_widget, 1)

        main_layout.addLayout(main_area_layout)

        self.setWindowTitle("Image Request Waitlist Manager")
        self.setGeometry(100, 100, 1200, 700)

        # Connect signals
        self.refresh_button.clicked.connect(self.refresh_data)
        self.filter_edit.textChanged.connect(self.filter_requests)
        self.view_orig_button.clicked.connect(lambda: self.view_image('original'))
        self.copy_orig_path_button.clicked.connect(lambda: self.copy_image_path('original'))
        self.view_proof_button.clicked.connect(lambda: self.view_image('proof'))
        self.upload_edited_button.clicked.connect(self.upload_edited_image)
        self.view_edited_button.clicked.connect(lambda: self.view_image('edited'))
        self.mark_complete_button.clicked.connect(self.mark_complete)
        self.send_email_button.clicked.connect(self.send_completion_email)

        self.disable_detail_buttons()

    def setup_model(self):
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
        self.table_model.refreshData()
        self.clear_details()
        self.disable_detail_buttons()
        print("Data refreshed from DB.")

    def filter_requests(self, text):
        search = QRegularExpression(text, QRegularExpression.PatternOption.CaseInsensitiveOption)
        self.proxy_model.setFilterRegularExpression(search)

    def on_selection_changed(self, selected, deselected):
        indexes = selected.indexes()
        if not indexes:
            self.clear_details()
            self.disable_detail_buttons()
            return
        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        row_data = self.table_model.getRowData(source_index.row())
        if row_data:
            self._current_request_id = row_data.get('id')
            self._current_request_data = row_data
            self.update_details_view(row_data)
            self.enable_detail_buttons(row_data)
        else:
            self.clear_details()
            self.disable_detail_buttons()

    def on_double_click(self, index):
        if not index.isValid() or not self._current_request_id:
            return
        self.view_image('original')

    def show_table_context_menu(self, position):
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            return
        menu = QMenu()
        view_orig_action = menu.addAction("View Original Image")
        copy_email_action = menu.addAction("Copy Email Address")
        copy_id_action = menu.addAction("Copy Request ID")
        mark_complete_action = menu.addAction("Mark as Completed")
        action = menu.exec(self.table_view.viewport().mapToGlobal(position))
        if action == view_orig_action:
            self.view_image('original')
        elif action == copy_email_action:
            self.copy_email()
        elif action == copy_id_action:
            self.copy_id()
        elif action == mark_complete_action:
            self.mark_complete()

    def update_details_view(self, data):
        self.details_header.setText("Details for Request")
        self.id_label.setText(data.get('id', 'N/A'))
        self.email_label.setText(data.get('email', 'N/A'))
        self.status_label.setText(data.get('status', 'N/A').capitalize())
        self.description_text.setText(data.get('description', ''))
        self.load_preview_image(self.original_image_label, data.get('original_image_path'))
        self.load_preview_image(self.proof_image_label, data.get('payment_proof_path'))
        self.load_preview_image(self.edited_image_label, data.get('edited_image_path'))

    def load_preview_image(self, label, relative_path):
        """Loads an image preview by fetching from the API."""
        label.setText("(Loading...)") # Indicate loading
        label.setPixmap(QPixmap()) # Clear existing
        label.setToolTip("") # Clear tooltip initially

        if not relative_path:
            label.setText("(No image)")
            return

        # Construct the full URL to the image endpoint
        # Ensure no double slashes and handle potential leading slash in relative_path
        image_url = f"{API_BASE_URL}/uploads/{relative_path.lstrip('/')}"
        label.setToolTip(f"URL:\n{image_url}") # Show URL on hover

        # --- Fetch image data using requests ---
        # !!! WARNING: Doing this directly in the UI thread WILL freeze the app
        #            while the image downloads. Use QThread for network requests
        #            in a production-quality application. This is simplified. !!!
        try:
            # Use stream=True for potentially large files, timeout is important
            response = requests.get(image_url, stream=True, timeout=10)
            response.raise_for_status() # Check for HTTP errors (4xx, 5xx)

            image_data = response.content # Read all image bytes
            pixmap = QPixmap()

            if pixmap.loadFromData(image_data):
                 # Successfully loaded image data into QPixmap
                 label.setPixmap(pixmap.scaled(label.size(),
                                            Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
                 # Tooltip already set to URL
            else:
                 label.setText("(Invalid Img Data)")
                 print(f"Warning: Could not load image data from {image_url} into QPixmap.")

        except requests.exceptions.Timeout:
             label.setText("(Timeout)")
             print(f"Warning: Timeout fetching image {image_url}")
        except requests.exceptions.ConnectionError:
             label.setText("(Conn Error)")
             print(f"Warning: Connection error fetching image {image_url}")
        except requests.exceptions.RequestException as e:
             label.setText("(Load Failed)")
             print(f"Warning: Failed to fetch image {image_url}: {e}")
             # Add status code if available
             if e.response is not None:
                  label.setToolTip(f"URL:\n{image_url}\nError: {e.response.status_code}")
        except Exception as e:
             label.setText("(Load Error)")
             print(f"Error loading image {image_url}: {e}")

    def get_image_api_url(self, image_type):
        """Gets the API URL for the selected request's image."""
        if not self._current_request_data: return None
        key_map = {
            'original': 'original_image_path',
            'proof': 'payment_proof_path',
            'edited': 'edited_image_path'
        }
        relative_path = self._current_request_data.get(key_map.get(image_type))
        if relative_path:
            # Ensure relative path doesn't have leading slash if API expects it that way
            relative_path = relative_path.lstrip('/')
            return f"{API_BASE_URL}/uploads/{relative_path}"
        return None
    
    def clear_details(self):
        self._current_request_id = None
        self._current_request_data = None
        self.details_header.setText("Select a request to view details")
        self.id_label.setText("-")
        self.email_label.setText("-")
        self.status_label.setText("-")
        self.description_text.clear()
        self.original_image_label.setText("Original Image")
        self.original_image_label.setPixmap(QPixmap())
        self.proof_image_label.setText("Payment Proof")
        self.proof_image_label.setPixmap(QPixmap())
        self.edited_image_label.setText("Edited Image")
        self.edited_image_label.setPixmap(QPixmap())
        self.disable_detail_buttons()

    def disable_detail_buttons(self):
        self.view_orig_button.setEnabled(False)
        self.copy_orig_path_button.setEnabled(False)
        self.view_proof_button.setEnabled(False)
        self.upload_edited_button.setEnabled(False)
        self.view_edited_button.setEnabled(False)
        self.mark_complete_button.setEnabled(False)
        self.copy_email_button.setEnabled(False)
        self.send_email_button.setEnabled(False)

    def enable_detail_buttons(self, data):
        status = data.get('status', 'pending')
        is_ready_to_complete = status not in ['pending_email', 'completed', 'email_sent']
        can_upload = status not in ['pending_email', 'completed', 'email_sent']
        is_pending_email = (status == 'pending_email')
        has_edited_image = bool(data.get('edited_image_path'))
        has_email = bool(data.get('email'))

        self.view_orig_button.setEnabled(bool(data.get('original_image_path')))
        self.copy_orig_path_button.setEnabled(bool(data.get('original_image_path')))
        self.view_proof_button.setEnabled(bool(data.get('payment_proof_path')))
        self.upload_edited_button.setEnabled(can_upload)
        self.view_edited_button.setEnabled(has_edited_image)
        self.mark_complete_button.setEnabled(is_ready_to_complete and has_edited_image)
        self.copy_email_button.setEnabled(has_email)
        self.send_email_button.setEnabled(is_pending_email)

    def get_full_image_path(self, image_type):
        if not self._current_request_data:
            return None
        key_map = {
            'original': 'original_image_path',
            'proof': 'payment_proof_path',
            'edited': 'edited_image_path'
        }
        relative_path = self._current_request_data.get(key_map.get(image_type))
        if relative_path:
            return relative_path
        return None

    def view_image(self, image_type):
        """Opens the image URL in the default system web browser."""
        image_url = self.get_image_api_url(image_type) # Use the new URL getter
        if image_url:
            print(f"Opening URL: {image_url}")
            if not QDesktopServices.openUrl(QUrl(image_url)):
                 QMessageBox.warning(self, "Open URL Failed", f"Could not open URL in browser:\n{image_url}")
        elif self._current_request_id:
             QMessageBox.information(self, "No Image", f"No {image_type} image URL found for this request.")

    def copy_to_clipboard(self, text):
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            print(f"Copied to clipboard: {text[:50]}...")
        else:
            print("Nothing to copy.")

    def copy_email(self):
        if self._current_request_data:
            self.copy_to_clipboard(self._current_request_data.get('email'))

    def copy_id(self):
        if self._current_request_data:
            self.copy_to_clipboard(self._current_request_data.get('id'))

    def copy_image_path(self, image_type):
        """Copies the relative server path (or full URL) to the clipboard."""
        # Option 1: Copy Relative Path (as stored in DB)
        if not self._current_request_data: return
        key_map = { 'original': 'original_image_path', 'proof': 'payment_proof_path', 'edited': 'edited_image_path' }
        relative_path = self._current_request_data.get(key_map.get(image_type))
        self.copy_to_clipboard(relative_path)

    def upload_edited_image(self):
        if not self._current_request_id:
            QMessageBox.warning(self, "No Request Selected", "Please select a request first.")
            return
        target_dir = EDITED_FOLDER
        fileName, _ = QFileDialog.getOpenFileName(self, "Select Edited Image", "",
                                                  "Image Files (*.png *.jpg *.jpeg *.gif *.webp)")
        if fileName:
            try:
                source_ext = os.path.splitext(fileName)[1].lower()
                if not source_ext:
                    source_ext = ".png"
                target_filename = f"{self._current_request_id}_edited{source_ext}"
                destination_path = posixpath.join(target_dir, target_filename)
                shutil.copy2(fileName, destination_path)
                relative_path = posixpath.join('edited', target_filename)
                if update_db_request(self._current_request_id, edited_path_relative=relative_path):
                    QMessageBox.information(self, "Upload Successful",
                                            f"Edited image saved as:\n{target_filename}")
                    self.refresh_data_and_reselect()
                else:
                    QMessageBox.warning(self, "Database Error",
                                        "Failed to update database with edited image path.")
                    if os.path.exists(destination_path):
                        os.remove(destination_path)
            except Exception as e:
                QMessageBox.critical(self, "Upload Failed",
                                     f"An error occurred during upload: {e}")
                print(f"Error uploading edited image: {e}")

    def mark_complete(self):
        if not self._current_request_id:
            QMessageBox.warning(self, "No Request Selected", "Please select a request first.")
            return
        if not self._current_request_data or not self._current_request_data.get('edited_image_path'):
            QMessageBox.warning(self, "Missing Edited Image",
                                "Cannot mark as complete without an uploaded edited image.")
            return
        current_status = self._current_request_data.get('status')
        if current_status in ['pending_email', 'completed', 'email_sent']:
            QMessageBox.information(self, "Already Processed",
                                    f"This request status is already '{current_status}'.")
            return
        reply = QMessageBox.question(self, 'Confirm Ready for Email',
                                     f"Mark request {self._current_request_id} as ready to send email?\n"
                                     f"Email: {self._current_request_data.get('email')}\n"
                                     "(Status will be set to 'pending_email')",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if update_db_request(self._current_request_id, status='pending_email'):
                QMessageBox.information(self, "Status Updated",
                                        "Request status set to 'pending_email'.\nYou can now send the completion email.")
                self.refresh_data_and_reselect()
            else:
                QMessageBox.warning(self, "Database Error", "Failed to update request status.")

    def send_completion_email(self):
        if not self._current_request_id or not self._current_request_data:
            QMessageBox.warning(self, "No Request Selected", "Please select a request first.")
            return
        status = self._current_request_data.get('status')
        recipient_email = self._current_request_data.get('email')
        if status != 'pending_email':
            QMessageBox.warning(self, "Invalid Status",
                                f"Request status is '{status}', not 'pending_email'. Cannot send email.")
            return
        if not recipient_email:
            QMessageBox.warning(self, "Missing Email",
                                "Cannot send: Recipient email address is missing for this request.")
            return
        reply = QMessageBox.question(self, 'Confirm Email Send',
                                     f"Send the completed image to:\n{recipient_email}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return
        request_id = self._current_request_id
        url = f"{API_BASE_URL}/send_completion_email/{request_id}"
        self.send_email_button.setEnabled(False)
        self.send_email_button.setText("Sending...")
        QApplication.processEvents()
        try:
            response = requests.post(url, timeout=45)
            if response.status_code == 200:
                QMessageBox.information(self, "Email Sent",
                                        response.json().get("message", "Email sent successfully."))
                self.refresh_data_and_reselect()
            else:
                try:
                    error_msg = response.json().get('error', 'Unknown error')
                except requests.exceptions.JSONDecodeError:
                    error_msg = response.text
                QMessageBox.critical(self, "Email Send Failed",
                                     f"Backend Error: {error_msg} (Status Code: {response.status_code})")
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "Connection/Request Error",
                                 f"Could not trigger email send:\n{e}")
        finally:
            self.send_email_button.setText("Send Completion Email")
            current_data = self.table_model.getRowData(
                self.table_view.currentIndex().row()) if self.table_view.currentIndex().isValid() else None
            if current_data:
                self.enable_detail_buttons(current_data)
            else:
                self.disable_detail_buttons()

    def refresh_data_and_reselect(self):
        current_id = self._current_request_id
        current_row = -1
        if self.table_view.currentIndex().isValid():
            current_row = self.table_view.currentIndex().row()
        self.table_model.refreshData()
        if current_id:
            new_proxy_index = QModelIndex()
            for row in range(self.proxy_model.rowCount()):
                source_index = self.proxy_model.mapToSource(self.proxy_model.index(row, 0))
                if self.table_model.data(source_index, Qt.ItemDataRole.DisplayRole) == current_id:
                    new_proxy_index = self.proxy_model.index(row, 0)
                    break
            if new_proxy_index.isValid():
                self.table_view.setCurrentIndex(new_proxy_index)
                self.table_view.scrollTo(new_proxy_index, QAbstractItemView.ScrollHint.EnsureVisible)
            elif current_row != -1 and current_row < self.proxy_model.rowCount():
                self.table_view.selectRow(current_row)
            else:
                self.clear_details()
        else:
            self.clear_details()

if __name__ == "__main__":
    os.makedirs(EDITED_FOLDER, exist_ok=True)
    app = QApplication(sys.argv)
    manager = WaitlistManager()
    manager.show()
    sys.exit(app.exec())
