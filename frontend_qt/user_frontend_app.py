import sys
import os
import requests # For making HTTP requests
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit,
    QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap
from dotenv import load_dotenv

load_dotenv()
# --- Configuration ---
BACKEND_SUBMIT_URL = f"{os.getenv("BACKEND_DOMAIN")}/submit"
PREVIEW_SIZE = 200 # Size for image previews in pixels

class UserFrontendApp(QWidget):
    def __init__(self):
        super().__init__()
        self._original_image_path = None
        self._proof_image_path = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Input Form ---
        form_layout = QGridLayout()
        form_layout.setSpacing(10)

        # Email Input
        form_layout.addWidget(QLabel("Your Email:"), 0, 0)
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter your email address")
        form_layout.addWidget(self.email_input, 0, 1, 1, 2) # Span 2 columns

        # Description Input
        form_layout.addWidget(QLabel("Request Details:"), 1, 0, Qt.AlignmentFlag.AlignTop)
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("(Optional) Describe the edit you want (e.g., 'Make it look like Van Gogh style')")
        self.description_input.setFixedHeight(80) # Limit height
        form_layout.addWidget(self.description_input, 1, 1, 1, 2)

        # Original Image Selection
        form_layout.addWidget(QLabel("Original Image:"), 2, 0, Qt.AlignmentFlag.AlignTop)
        self.original_image_preview = QLabel("No image selected")
        self.original_image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_image_preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.original_image_preview.setStyleSheet("border: 1px solid gray;")
        browse_orig_button = QPushButton("Browse...")
        browse_orig_button.clicked.connect(self.browse_original_image)
        orig_image_layout = QVBoxLayout()
        orig_image_layout.addWidget(self.original_image_preview)
        orig_image_layout.addWidget(browse_orig_button)
        form_layout.addLayout(orig_image_layout, 2, 1)

        # Payment Proof Selection
        form_layout.addWidget(QLabel("Payment Proof:"), 2, 2, Qt.AlignmentFlag.AlignTop) # Place next to original image
        self.proof_image_preview = QLabel("No proof selected")
        self.proof_image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.proof_image_preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.proof_image_preview.setStyleSheet("border: 1px solid gray;")
        browse_proof_button = QPushButton("Browse...")
        browse_proof_button.clicked.connect(self.browse_proof_image)
        proof_image_layout = QVBoxLayout()
        proof_image_layout.addWidget(self.proof_image_preview)
        proof_image_layout.addWidget(browse_proof_button)
        form_layout.addLayout(proof_image_layout, 2, 3) # Column index 3

        # Make image columns take available space
        form_layout.setColumnStretch(1, 1)
        form_layout.setColumnStretch(3, 1)


        main_layout.addLayout(form_layout)
        main_layout.addStretch() # Pushes button and status to bottom

        # --- Submit Area ---
        self.status_label = QLabel("") # For feedback messages
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.submit_button = QPushButton("Submit Request")
        self.submit_button.setStyleSheet("background-color: lightgreen; font-size: 16px; padding: 10px;")
        self.submit_button.clicked.connect(self.submit_request)

        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.submit_button)

        # --- Window Properties ---
        self.setWindowTitle("AI Image Edit Request")
        self.setGeometry(150, 150, 650, 500) # Position and size

    def browse_image(self, is_original):
        """Opens file dialog and updates path and preview."""
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("Images (*.png *.jpg *.jpeg *.gif *.webp)")
        file_dialog.setViewMode(QFileDialog.ViewMode.Detail)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

        if file_dialog.exec():
            filenames = file_dialog.selectedFiles()
            if filenames:
                filepath = filenames[0]
                if is_original:
                    self._original_image_path = filepath
                    self.update_preview(self.original_image_preview, filepath, "Original Image")
                else:
                    self._proof_image_path = filepath
                    self.update_preview(self.proof_image_preview, filepath, "Payment Proof")

    def browse_original_image(self):
        self.browse_image(is_original=True)

    def browse_proof_image(self):
        self.browse_image(is_original=False)

    def update_preview(self, label_widget, filepath, placeholder_text):
        """Loads image into the specified QLabel."""
        if filepath and os.path.exists(filepath):
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(PREVIEW_SIZE, PREVIEW_SIZE,
                                             Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)
                label_widget.setPixmap(scaled_pixmap)
                label_widget.setToolTip(filepath) # Show full path on hover
            else:
                label_widget.setText("(Invalid Image)")
                label_widget.setPixmap(QPixmap()) # Clear pixmap
                if label_widget == self.original_image_preview: self._original_image_path = None
                else: self._proof_image_path = None
        else:
            label_widget.setText(placeholder_text)
            label_widget.setPixmap(QPixmap())
            if label_widget == self.original_image_preview: self._original_image_path = None
            else: self._proof_image_path = None

    def submit_request(self):
        """Validates input and sends data to the backend."""
        email = self.email_input.text().strip()
        description = self.description_input.toPlainText().strip()

        # --- Validation ---
        if not email:
            QMessageBox.warning(self, "Input Error", "Please enter your email address.")
            return
        if not self._original_image_path:
            QMessageBox.warning(self, "Input Error", "Please select the original image.")
            return
        if not self._proof_image_path:
            QMessageBox.warning(self, "Input Error", "Please select the payment proof image.")
            return

        # --- Prepare data for POST request ---
        # Must match the names expected by the Flask backend's request.form and request.files
        form_data = {
            'email': email,
            'description': description,
        }

        try:
             # Open files in binary mode ('rb') for upload
             # Using 'with' ensures files are closed automatically
             with open(self._original_image_path, 'rb') as img_file, \
                  open(self._proof_image_path, 'rb') as proof_file:

                files_data = {
                    'image': (os.path.basename(self._original_image_path), img_file, 'image/jpeg'), # You can adjust mime type if needed
                    'payment_proof': (os.path.basename(self._proof_image_path), proof_file, 'image/jpeg')
                }

                # --- Disable button and show status ---
                self.submit_button.setEnabled(False)
                self.status_label.setText("Submitting request...")
                QApplication.processEvents() # Update UI

                # --- Send Request ---
                response = requests.post(BACKEND_SUBMIT_URL, data=form_data, files=files_data, timeout=30) # 30 second timeout

                # --- Handle Response ---
                if response.status_code == 201: # Created (Success as defined in backend)
                    response_data = response.json()
                    request_id = response_data.get('request_id', 'N/A')
                    QMessageBox.information(self, "Success", f"Request submitted successfully!\nYour Request ID: {request_id}")
                    self.status_label.setText(f"Success! Request ID: {request_id}")
                    # Optionally clear the form
                    self.clear_form()
                elif response.status_code == 429: # Too Many Requests (Rate Limit)
                     QMessageBox.warning(self, "Rate Limited", "You are submitting too frequently. Please wait a moment and try again.")
                     self.status_label.setText("Error: Rate Limited.")
                else:
                    # Try to get error message from backend JSON
                    try:
                        error_msg = response.json().get('error', 'Unknown error')
                    except requests.exceptions.JSONDecodeError:
                        error_msg = response.text # Use raw text if not JSON
                    QMessageBox.critical(self, "Submission Failed", f"Error: {error_msg} (Status Code: {response.status_code})")
                    self.status_label.setText(f"Error: {error_msg}")

        except FileNotFoundError as e:
             QMessageBox.critical(self, "File Error", f"Could not find file: {e.filename}")
             self.status_label.setText("Error: File not found.")
        except requests.exceptions.ConnectionError:
            QMessageBox.critical(self, "Connection Error", f"Could not connect to the backend at\n{BACKEND_SUBMIT_URL}\n\nPlease ensure the backend server is running.")
            self.status_label.setText("Error: Cannot connect to server.")
        except requests.exceptions.Timeout:
             QMessageBox.critical(self, "Timeout Error", "The request timed out. The server might be busy or unresponsive.")
             self.status_label.setText("Error: Request timed out.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
            self.status_label.setText(f"Error: {e}")
            print(f"Unexpected error during submission: {e}") # Log for debugging

        finally:
            # --- Re-enable button ---
            self.submit_button.setEnabled(True)
            # Keep the status label showing the final result unless clearing the form

    def clear_form(self):
        """Resets the form fields and image selections."""
        self.email_input.clear()
        self.description_input.clear()
        self._original_image_path = None
        self._proof_image_path = None
        self.update_preview(self.original_image_preview, None, "No image selected")
        self.update_preview(self.proof_image_preview, None, "No proof selected")
        # Optionally clear status label after a delay, or keep it showing success/last error
        # self.status_label.setText("")


# --- Run Application ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    frontend = UserFrontendApp()
    frontend.show()
    sys.exit(app.exec())