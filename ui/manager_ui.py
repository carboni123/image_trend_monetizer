import sys
import os
import sqlite3
import shutil
import requests 
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

# --- Configuration ---
# IMPORTANT: Adjust this path if UI is run from a different location relative to backend
DATABASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'waitlist.db'))
UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'uploads'))
EDITED_FOLDER = os.path.join(UPLOAD_FOLDER, 'edited')

BACKEND_BASE_URL = 'http://127.0.0.1:5000' # Change if backend is elsewhere

# --- Database Access ---
# Reusing context manager concept from backend's database.py
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def fetch_requests_from_db():
    """Fetches all requests."""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute('SELECT id, email, description, status, submitted_at, completed_at, original_image_path, payment_proof_path, edited_image_path FROM requests ORDER BY submitted_at DESC')
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error fetching requests: {e}")
        QMessageBox.critical(None, "Database Error", f"Could not fetch requests: {e}")
        return []

def update_db_request(req_id, status=None, edited_path_relative=None):
    """Updates a request in the database."""
    try:
        with get_db_connection() as conn:
            updates = []
            params = []
            if status:
                updates.append("status = ?")
                params.append(status)
            if edited_path_relative is not None: # Allow clearing path with empty string
                updates.append("edited_image_path = ?")
                params.append(edited_path_relative)
            if status == 'completed':
                updates.append("completed_at = CURRENT_TIMESTAMP")

            if not updates:
                return False # Nothing to update

            sql = f"UPDATE requests SET {', '.join(updates)} WHERE id = ?"
            params.append(req_id)
            conn.execute(sql, tuple(params))
            conn.commit()
            return conn.total_changes > 0
    except Exception as e:
        print(f"Error updating request {req_id}: {e}")
        QMessageBox.critical(None, "Database Error", f"Could not update request {req_id}: {e}")
        return False


# --- Table Model ---
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
        col_name = self.COLUMNS[col_index].lower().replace(" ", "_") # Guess key from header

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
                    if isinstance(value, str) and ('_at' in key_to_find):
                         # Attempt to parse timestamp string for consistent formatting
                         try:
                             dt = QDateTime.fromString(value.split('.')[0], "yyyy-MM-dd HH:mm:ss")
                             if dt.isValid():
                                 return dt.toString(self.DATETIME_FORMAT)
                             else: # Handle potential CURRENT_TIMESTAMP format
                                dt_ts = QDateTime.fromString(value, Qt.DateFormat.ISODateWithMs)
                                if dt_ts.isValid():
                                    return dt_ts.toString(self.DATETIME_FORMAT)
                                return value # Fallback if parsing fails
                         except Exception:
                             return value # Fallback
                    return str(value) if value is not None else ""
                else:
                    return "" # Should not happen if COLUMN_MAP is correct

            elif role == Qt.ItemDataRole.UserRole: # To get the full row data
                return row_data

        except IndexError:
            return None # Should not happen
        except KeyError:
            return "" # Handle if a key is unexpectedly missing

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

        # Example: Try converting to QDateTime for sorting Submitted/Completed columns
        col = left.column()
        if col in [WaitlistTableModel.COLUMN_MAP["submitted_at"], WaitlistTableModel.COLUMN_MAP["completed_at"]]:
            left_dt = QDateTime.fromString(left_data, WaitlistTableModel.DATETIME_FORMAT)
            right_dt = QDateTime.fromString(right_data, WaitlistTableModel.DATETIME_FORMAT)
            if left_dt.isValid() and right_dt.isValid():
                return left_dt < right_dt
            elif left_dt.isValid(): # Valid dates come before invalid/null
                 return True
            elif right_dt.isValid():
                 return False
            # Fallback to string comparison if parsing fails or values are None/empty
            return str(left_data) < str(right_data)

        # Default comparison for other columns
        return super().lessThan(left, right)


# --- Main UI Window ---
class WaitlistManager(QWidget):
    def __init__(self):
        super().__init__()
        self._current_request_id = None
        self._current_request_data = None
        self.copy_email_button = None
        self.send_email_button = None
        self.init_ui()
        self.setup_model()
        self.refresh_data() # Load initial data

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
        self.description_text.setMaximumHeight(80) # Limit height
        details_grid.addWidget(self.description_text, 3, 1, 1, 2) # Span 2 columns

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
        details_layout.addStretch() # Push button to bottom

        # Action Buttons at the bottom of details panel
        action_button_layout = QHBoxLayout()

        self.mark_complete_button = QPushButton("Mark as Completed")
        self.mark_complete_button.setStyleSheet("background-color: lightgreen;")
        action_button_layout.addWidget(self.mark_complete_button)

        # --- ADD SEND EMAIL BUTTON ---
        self.send_email_button = QPushButton("Send Completion Email")
        self.send_email_button.setStyleSheet("background-color: lightblue;") # Style differently
        action_button_layout.addWidget(self.send_email_button)

        details_layout.addLayout(action_button_layout) # Add the layout containing both buttons

        details_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        main_area_layout.addWidget(details_widget, 1) # Give details less space initially

        main_layout.addLayout(main_area_layout)

        # Window properties
        self.setWindowTitle("Image Request Waitlist Manager")
        self.setGeometry(100, 100, 1200, 700) # Adjust size as needed

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

        # Disable buttons initially
        self.disable_detail_buttons()

    def setup_model(self):
        """Creates the table model and proxy model."""
        self.table_model = WaitlistTableModel()
        self.proxy_model = RequestFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True) # Enable sorting on the proxy model

        # Adjust column widths
        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["id"], QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["status"], QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["email"], QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["submitted_at"], QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["completed_at"], QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WaitlistTableModel.COLUMN_MAP["description"], QHeaderView.ResizeMode.Stretch) # Let description take remaining space
        self.table_view.setColumnWidth(WaitlistTableModel.COLUMN_MAP["email"], 180) # Example fixed width


        # Connect selection change AFTER model is set
        self.table_view.selectionModel().selectionChanged.connect(self.on_selection_changed)
        self.table_view.doubleClicked.connect(self.on_double_click)

        # Add context menu
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_table_context_menu)


    def refresh_data(self):
        """Reloads data from the database into the table."""
        self.table_model.refreshData()
        self.clear_details()
        self.disable_detail_buttons()
        print("Data refreshed.")

    def filter_requests(self, text):
        """Applies the filter text to the proxy model."""
        search = QRegularExpression(text, QRegularExpression.PatternOption.CaseInsensitiveOption)
        self.proxy_model.setFilterRegularExpression(search)

    def on_selection_changed(self, selected, deselected):
        """Updates the details panel when table selection changes."""
        indexes = selected.indexes()
        if not indexes:
            self.clear_details()
            self.disable_detail_buttons()
            return

        # Get the source model index from the proxy model index
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
        """Handles double-clicking a row (e.g., open original image)."""
        if not index.isValid() or not self._current_request_id:
             return
        self.view_image('original') # Default double-click action

    def show_table_context_menu(self, position):
        """Shows a context menu for the table."""
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            return

        menu = QMenu()
        view_orig_action = menu.addAction("View Original Image")
        copy_email_action = menu.addAction("Copy Email Address")
        copy_id_action = menu.addAction("Copy Request ID")
        mark_complete_action = menu.addAction("Mark as Completed")
        # Add more actions as needed

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
        """Populates the details panel with data from the selected row."""
        self.details_header.setText(f"Details for Request") # Remove ID here, it's below
        self.id_label.setText(data.get('id', 'N/A'))
        self.email_label.setText(data.get('email', 'N/A'))
        self.status_label.setText(data.get('status', 'N/A').capitalize())
        self.description_text.setText(data.get('description', ''))

        # Load image previews (handle missing files gracefully)
        self.load_preview_image(self.original_image_label, data.get('original_image_path'))
        self.load_preview_image(self.proof_image_label, data.get('payment_proof_path'))
        self.load_preview_image(self.edited_image_label, data.get('edited_image_path'))

    def load_preview_image(self, label, relative_path):
        """Loads an image into a QLabel as a scaled pixmap."""
        if not relative_path:
            label.setText("(No image)")
            label.setPixmap(QPixmap()) # Clear existing pixmap
            return

        full_path = os.path.join(UPLOAD_FOLDER, relative_path)
        if os.path.exists(full_path):
            pixmap = QPixmap(full_path)
            if not pixmap.isNull():
                 label.setPixmap(pixmap.scaled(label.size(),
                                            Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
                 label.setToolTip(full_path) # Show full path on hover
                 return
            else:
                label.setText("(Invalid Img)")
                label.setPixmap(QPixmap())
                print(f"Warning: Could not load image {full_path}")
        else:
            label.setText("(Not Found)")
            label.setPixmap(QPixmap())
            print(f"Warning: Image path not found {full_path}")


    def clear_details(self):
        """Clears the information in the details panel."""
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
        """Disables all buttons in the details panel."""
        self.view_orig_button.setEnabled(False)
        self.copy_orig_path_button.setEnabled(False)
        self.view_proof_button.setEnabled(False)
        self.upload_edited_button.setEnabled(False)
        self.view_edited_button.setEnabled(False)
        self.mark_complete_button.setEnabled(False)
        self.copy_email_button.setEnabled(False)
        self.send_email_button.setEnabled(False)

    def enable_detail_buttons(self, data):
        """Enables buttons based on the selected request's data."""
        status = data.get('status', 'pending')
        # Determine states relevant to buttons
        is_ready_to_complete = status not in ['pending_email', 'completed', 'email_sent'] # Add any final states here
        can_upload = status not in ['pending_email', 'completed', 'email_sent']
        is_pending_email = (status == 'pending_email')
        has_edited_image = bool(data.get('edited_image_path'))
        has_email = bool(data.get('email'))

        self.view_orig_button.setEnabled(bool(data.get('original_image_path')))
        self.copy_orig_path_button.setEnabled(bool(data.get('original_image_path')))
        self.view_proof_button.setEnabled(bool(data.get('payment_proof_path')))
        # Enable upload if not in a final/pending email state
        self.upload_edited_button.setEnabled(can_upload)
        # Enable view edited if path exists
        self.view_edited_button.setEnabled(has_edited_image)
        # Enable "Mark Complete" (to set to pending_email) only if it's ready AND has edited image
        self.mark_complete_button.setEnabled(is_ready_to_complete and has_edited_image)

        self.copy_email_button.setEnabled(has_email)
        self.send_email_button.setEnabled(is_pending_email)

    def get_full_image_path(self, image_type):
        """Gets the full path for the selected request's image."""
        if not self._current_request_data: return None
        key_map = {
            'original': 'original_image_path',
            'proof': 'payment_proof_path',
            'edited': 'edited_image_path'
        }
        relative_path = self._current_request_data.get(key_map.get(image_type))
        if relative_path:
            return os.path.join(UPLOAD_FOLDER, relative_path)
        return None

    def view_image(self, image_type):
        """Opens the specified image using the default system viewer."""
        full_path = self.get_full_image_path(image_type)
        if full_path and os.path.exists(full_path):
            # Use QDesktopServices for cross-platform opening
            url = QUrl.fromLocalFile(full_path)
            if not QDesktopServices.openUrl(url):
                 QMessageBox.warning(self, "Open Failed", f"Could not open image file:\n{full_path}")
        elif self._current_request_id:
             QMessageBox.information(self, "No Image", f"No {image_type} image found for this request.")

    def copy_to_clipboard(self, text):
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            print(f"Copied to clipboard: {text[:50]}...") # Log snippet
        else:
             print("Nothing to copy.")

    def copy_email(self):
        if self._current_request_data:
            self.copy_to_clipboard(self._current_request_data.get('email'))

    def copy_id(self):
         if self._current_request_data:
            self.copy_to_clipboard(self._current_request_data.get('id'))

    def copy_image_path(self, image_type):
        full_path = self.get_full_image_path(image_type)
        self.copy_to_clipboard(full_path)


    def upload_edited_image(self):
        """Opens a dialog to select and save the edited image."""
        if not self._current_request_id:
            QMessageBox.warning(self, "No Request Selected", "Please select a request first.")
            return

        target_dir = EDITED_FOLDER # Save directly to the designated edited folder

        fileName, _ = QFileDialog.getOpenFileName(self, "Select Edited Image", "", "Image Files (*.png *.jpg *.jpeg *.gif *.webp)")

        if fileName:
            try:
                # Determine the extension
                source_ext = os.path.splitext(fileName)[1].lower()
                if not source_ext: source_ext = ".png" # Default if no extension

                # Create a unique name within the edited folder
                target_filename = f"{self._current_request_id}_edited{source_ext}"
                destination_path = os.path.join(target_dir, target_filename)

                # Copy the selected file to the edited folder
                shutil.copy2(fileName, destination_path) # copy2 preserves metadata

                # Update the database with the relative path
                relative_path = os.path.join('edited', target_filename)
                if update_db_request(self._current_request_id, edited_path_relative=relative_path):
                    QMessageBox.information(self, "Upload Successful", f"Edited image saved as:\n{target_filename}")
                    self.refresh_data_and_reselect() # Refresh to show the update in table/details
                    # Optionally re-select the same row if needed
                else:
                    QMessageBox.warning(self, "Database Error", "Failed to update database with edited image path.")
                    # Consider removing the copied file if DB update fails
                    if os.path.exists(destination_path): os.remove(destination_path)

            except Exception as e:
                QMessageBox.critical(self, "Upload Failed", f"An error occurred during upload: {e}")
                print(f"Error uploading edited image: {e}")


    def mark_complete(self):
        """Marks the selected request as completed in the database."""
        if not self._current_request_id:
             QMessageBox.warning(self, "No Request Selected", "Please select a request first.")
             return
        if not self._current_request_data or not self._current_request_data.get('edited_image_path'):
             QMessageBox.warning(self, "Missing Edited Image", "Cannot mark as complete without an uploaded edited image.")
             return

        current_status = self._current_request_data.get('status')
        if current_status in ['pending_email', 'completed', 'email_sent']:
            QMessageBox.information(self, "Already Processed", f"This request status is already '{current_status}'.")
            return

        reply = QMessageBox.question(self, 'Confirm Ready for Email', # Changed dialog title/text slightly
                                     f"Mark request {self._current_request_id} as ready to send email?\n"
                                     f"Email: {self._current_request_data.get('email')}\n"
                                     "(Status will be set to 'pending_email')",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # Update status to 'pending_email'
            if update_db_request(self._current_request_id, status='pending_email'):
                QMessageBox.information(self, "Status Updated", "Request status set to 'pending_email'.\nYou can now send the completion email.")
                self.refresh_data_and_reselect() # Refresh list and re-enable buttons correctly
            else:
                 QMessageBox.warning(self, "Database Error", "Failed to update request status.")

    def send_completion_email(self):
        """Triggers the backend endpoint to send the completion email."""
        if not self._current_request_id or not self._current_request_data:
             QMessageBox.warning(self, "No Request Selected", "Please select a request first.")
             return

        status = self._current_request_data.get('status')
        recipient_email = self._current_request_data.get('email')

        if status != 'pending_email':
             QMessageBox.warning(self, "Invalid Status", f"Request status is '{status}', not 'pending_email'. Cannot send email.")
             return
        if not recipient_email:
            QMessageBox.warning(self, "Missing Email", "Cannot send: Recipient email address is missing for this request.")
            return

        # Confirmation Dialog
        reply = QMessageBox.question(self, 'Confirm Email Send',
                                     f"Send the completed image to:\n{recipient_email}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            return

        # Prepare for backend call
        request_id = self._current_request_id
        url = f"{BACKEND_BASE_URL}/send_completion_email/{request_id}"

        # Disable button and show status (optional, good for UX)
        self.send_email_button.setEnabled(False)
        self.send_email_button.setText("Sending...")
        QApplication.processEvents() # Force UI update

        try:
            response = requests.post(url, timeout=45) # Increased timeout for email sending

            if response.status_code == 200:
                QMessageBox.information(self, "Email Sent", response.json().get("message", "Email sent successfully."))
                self.refresh_data_and_reselect() # Refresh to show final status and disable buttons correctly
            else:
                # Handle backend errors (like backend still checking for 'completed' status)
                try:
                    error_msg = response.json().get('error', 'Unknown error')
                except requests.exceptions.JSONDecodeError:
                    error_msg = response.text
                QMessageBox.critical(self, "Email Send Failed", f"Backend Error: {error_msg} (Status Code: {response.status_code})")

        except requests.exceptions.ConnectionError:
            QMessageBox.critical(self, "Connection Error", f"Could not connect to the backend at\n{url}")
        except requests.exceptions.Timeout:
             QMessageBox.critical(self, "Timeout Error", "The request timed out. Email sending might be slow or failing.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
            print(f"Unexpected error during email send trigger: {e}") # Log for debugging

        finally:
             # Restore button text
             self.send_email_button.setText("Send Completion Email")
             # Re-evaluate button enablement based on potentially refreshed data
             # Need to fetch the potentially updated data if refresh didn't happen on error
             current_data = self.table_model.getRowData(self.table_view.currentIndex().row()) if self.table_view.currentIndex().isValid() else None
             if current_data:
                 self.enable_detail_buttons(current_data)
             else:
                 # If selection was lost or row vanished, disable everything
                 self.disable_detail_buttons()


    # --- HELPER: Refresh data and try to reselect the current row ---
    def refresh_data_and_reselect(self):
        """Refreshes data and attempts to re-select the previously selected item."""
        current_id = self._current_request_id
        current_row = -1
        if self.table_view.currentIndex().isValid():
            current_row = self.table_view.currentIndex().row() # Proxy model row

        # Store scroll position if needed
        # scroll_bar = self.table_view.verticalScrollBar()
        # old_scroll_value = scroll_bar.value()

        self.table_model.refreshData()

        if current_id:
            # Find the new proxy index for the old ID
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
                 # Fallback: select the same row index if ID not found (might be different item)
                 self.table_view.selectRow(current_row)
            else:
                 self.clear_details() # Clear details if selection lost
        else:
            self.clear_details() # Clear details if nothing was selected

            
# --- Run Application ---
if __name__ == "__main__":
    # Check if DB exists before starting UI
    if not os.path.exists(DATABASE_PATH):
         print(f"ERROR: Database file not found at {DATABASE_PATH}")
         print("Please run the backend server (`python backend/app.py`) at least once to initialize the database.")
         sys.exit(1)
    # Ensure edited folder exists for UI uploads
    os.makedirs(EDITED_FOLDER, exist_ok=True)

    app = QApplication(sys.argv)
    manager = WaitlistManager()
    manager.show()
    sys.exit(app.exec())