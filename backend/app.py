import os
import uuid
import mimetypes
from flask import Flask, request, jsonify, current_app
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail, Message # Import Mail and Message
from dotenv import load_dotenv # Import dotenv

# --- Project Specific Imports ---
import database

# --- Load Environment Variables ---
load_dotenv() # Load variables from .env file

# --- Configuration ---
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ORIGINAL_FOLDER = os.path.join(UPLOAD_FOLDER, 'original')
PROOF_FOLDER = os.path.join(UPLOAD_FOLDER, 'proof')
EDITED_FOLDER = os.path.join(UPLOAD_FOLDER, 'edited')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# --- App Initialization ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Flask-Mail Configuration ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-fallback-secret-key') # Needed by Flask and extensions
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD') # Use App Password if 2FA enabled
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

# Check if mail configuration is present
if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
    print("\n*** WARNING: MAIL_USERNAME or MAIL_PASSWORD not found in environment variables. Email sending will likely fail. ***\n")

mail = Mail(app) # Initialize Flask-Mail

# --- Rate Limiting ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour", "5 per minute"] # Adjust as needed
)

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def setup_directories():
    """Creates necessary upload directories if they don't exist."""
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(ORIGINAL_FOLDER, exist_ok=True)
    os.makedirs(PROOF_FOLDER, exist_ok=True)
    os.makedirs(EDITED_FOLDER, exist_ok=True)
    print("Upload directories ensured.")

# --- Routes ---
@app.route('/submit', methods=['POST'])
@limiter.limit("3 per minute") # Stricter limit for submission
def submit_request():
    if 'email' not in request.form or not request.form['email']:
        return jsonify({"error": "Email is required"}), 400
    if 'image' not in request.files:
        return jsonify({"error": "Original image is required"}), 400
    if 'payment_proof' not in request.files:
        return jsonify({"error": "Payment proof image is required"}), 400

    email = request.form['email']
    description = request.form.get('description', '') # Optional
    image_file = request.files['image']
    proof_file = request.files['payment_proof']

    if not allowed_file(image_file.filename) or not allowed_file(proof_file.filename):
        return jsonify({"error": "Invalid file type. Allowed: png, jpg, jpeg, gif, webp"}), 400

    # Generate unique ID and secure filenames
    request_id = str(uuid.uuid4())
    image_ext = image_file.filename.rsplit('.', 1)[1].lower()
    proof_ext = proof_file.filename.rsplit('.', 1)[1].lower()

    image_filename = secure_filename(f"{request_id}_original.{image_ext}")
    proof_filename = secure_filename(f"{request_id}_proof.{proof_ext}")

    image_path = os.path.join(ORIGINAL_FOLDER, image_filename)
    proof_path = os.path.join(PROOF_FOLDER, proof_filename)

    try:
        image_file.save(image_path)
        proof_file.save(proof_path)

        # Store relative paths or just filenames if backend & UI share base path knowledge
        db_image_path = os.path.join('original', image_filename)
        db_proof_path = os.path.join('proof', proof_filename)

        database.add_request(request_id, email, description, db_image_path, db_proof_path)

        return jsonify({"message": "Request received successfully", "request_id": request_id}), 201

    except Exception as e:
        # Basic cleanup if DB insertion fails after saving files
        if os.path.exists(image_path):
            os.remove(image_path)
        if os.path.exists(proof_path):
            os.remove(proof_path)
        app.logger.error(f"Error processing request: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    # Basic health check
    try:
        # Try a quick DB connection
        with database.get_db_connection() as conn:
            conn.execute("SELECT 1")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        app.logger.error(f"Health check failed: {e}")
        return jsonify({"status": "error", "details": str(e)}), 500

@app.route('/send_completion_email/<string:request_id>', methods=['POST'])
@limiter.limit("10 per hour") # Limit email sending rate
def send_completion_email(request_id):
    if not request_id:
        return jsonify({"error": "Request ID is required"}), 400

    app.logger.info(f"Received request to send completion email for ID: {request_id}")

    # 1. Fetch request details from DB
    request_data = database.get_request_by_id(request_id)

    if not request_data:
        app.logger.error(f"Request ID not found: {request_id}")
        return jsonify({"error": "Request not found"}), 404

    # 2. Validate request status and data
    recipient_email = request_data.get('email')
    relative_edited_path = request_data.get('edited_image_path')
    status = request_data.get('status')

    if status != 'pending_email':
         app.logger.warning(f"Attempt to send email for non-completed request ID: {request_id} (Status: {status})")
         return jsonify({"error": f"Request status is '{status}', not 'completed'. Cannot send email yet."}), 400
    if not recipient_email:
         app.logger.error(f"Missing recipient email for request ID: {request_id}")
         return jsonify({"error": "Recipient email missing for this request"}), 400
    if not relative_edited_path:
        app.logger.error(f"Missing edited image path for request ID: {request_id}")
        return jsonify({"error": "Edited image path missing for this request"}), 400

    # 3. Construct full image path
    full_edited_path = os.path.join(app.config['UPLOAD_FOLDER'], relative_edited_path)
    if not os.path.exists(full_edited_path):
        app.logger.error(f"Edited image file not found at path: {full_edited_path}")
        return jsonify({"error": "Edited image file not found on server"}), 404

    # 4. Prepare Email
    subject = "Your AI Image Edit is Ready!"
    # Basic email body - customize as needed
    body_text = f"Hello,\n\nYour requested image edit (ID: {request_id}) is complete.\nPlease find the edited image attached.\n\nThank you!"
    body_html = f"""
    <p>Hello,</p>
    <p>Your requested image edit (ID: <strong>{request_id}</strong>) is complete.</p>
    <p>Please find the edited image attached.</p>
    <p>Thank you!</p>
    """

    msg = Message(subject, recipients=[recipient_email])
    msg.body = body_text
    msg.html = body_html

    # 5. Attach the image
    try:
        with app.open_resource(full_edited_path, "rb") as fp:
            # Guess MIME type based on file extension
            content_type, _ = mimetypes.guess_type(full_edited_path)
            if content_type is None:
                content_type = 'application/octet-stream' # Default if guess fails
            filename = os.path.basename(full_edited_path)
            msg.attach(filename=filename, content_type=content_type, data=fp.read())
            app.logger.info(f"Attached file '{filename}' with type '{content_type}' to email for {recipient_email}.")
    except Exception as e:
        app.logger.error(f"Error attaching file {full_edited_path} for request {request_id}: {e}")
        return jsonify({"error": f"Failed to read or attach image file: {e}"}), 500

    # 6. Send Email
    try:
        app.logger.info(f"Attempting to send email via {app.config['MAIL_SERVER']} to {recipient_email} for request {request_id}...")
        mail.send(msg)
        app.logger.info(f"Email sent successfully to {recipient_email} for request {request_id}.")

        # --- ADDED: Update DB status to 'completed' AFTER sending ---
        if database.update_request_status(request_id, status='completed'):
             app.logger.info(f"Successfully updated status to 'completed' for request {request_id} after sending email.")
        else:
             # Log a warning but don't fail the request, as the email *was* sent.
             app.logger.warning(f"Email sent for {request_id}, but failed to update status to 'completed' in DB.")
        # --- END ADDED ---

        return jsonify({"message": f"Email sent successfully to {recipient_email}"}), 200

    except Exception as e:
        app.logger.error(f"Failed to send email for request {request_id} to {recipient_email}: {e}")
        return jsonify({"error": f"Failed to send email. Check server logs for details. Error: {e}"}), 500
    
    
# --- Main Execution ---
if __name__ == '__main__':
    print("Starting backend server...")
    database.init_db()    # Initialize DB schema on startup
    setup_directories() # Create upload folders on startup
    # Use host='0.0.0.0' to make it accessible on your network
    # Use debug=True only for development, False for production-like testing
    app.run(host='0.0.0.0', port=5000, debug=True)