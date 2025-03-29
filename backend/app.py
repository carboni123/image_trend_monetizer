import os
import uuid
from flask import Flask, request, jsonify, Response, current_app
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail, Message
from dotenv import load_dotenv
import logging
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

# --- Project Specific Imports ---
import database

# --- Load Environment Variables ---
load_dotenv()

# --- App Initialization ---
app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# --- Flask-Mail Configuration ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-fallback-secret-key')
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
    print("\n*** WARNING: MAIL_USERNAME or MAIL_PASSWORD not found in environment variables. Email sending will likely fail. ***\n")

mail = Mail(app)

# --- MinIO Configuration ---
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY')
MINIO_BUCKET_NAME = os.getenv('MINIO_BUCKET_NAME')

if not all([MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET_NAME]):
    print("\n*** WARNING: MinIO environment variables not fully set. File storage will not work. ***\n")
    s3_client = None
else:
    s3_client = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4')
    )

# --- Rate Limiting ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour", "5 per minute"]
)

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# --- Routes ---
@app.route('/submit', methods=['POST'])
@limiter.limit("3 per minute")
def submit_request():
    if s3_client is None:
        return jsonify({"error": "MinIO is not configured"}), 500

    if 'email' not in request.form or not request.form['email']:
        return jsonify({"error": "Email is required"}), 400
    if 'image' not in request.files:
        return jsonify({"error": "Original image is required"}), 400
    if 'payment_proof' not in request.files:
        return jsonify({"error": "Payment proof image is required"}), 400

    email = request.form['email']
    description = request.form.get('description', '')
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

    # Define MinIO object keys
    image_object_key = f"original/{image_filename}"
    proof_object_key = f"proof/{proof_filename}"

    try:
        # Upload files to MinIO
        s3_client.upload_fileobj(image_file, MINIO_BUCKET_NAME, image_object_key)
        s3_client.upload_fileobj(proof_file, MINIO_BUCKET_NAME, proof_object_key)

        # Store object keys in database
        database.add_request(request_id, email, description, image_object_key, proof_object_key)

        return jsonify({"message": "Request received successfully", "request_id": request_id}), 201

    except ClientError as e:
        app.logger.error(f"MinIO upload error: {e}")
        return jsonify({"error": "Failed to upload files to MinIO"}), 500
    except Exception as e:
        app.logger.error(f"Error processing request: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    db_ok = False
    try:
        with database.get_db_connection() as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception as e:
        app.logger.error(f"Database health check failed: {e}")
    return jsonify({"status": "ok" if db_ok else "error", "database": "ok" if db_ok else "error"}), 200 if db_ok else 500

@app.route('/send_completion_email/<string:request_id>', methods=['POST'])
@limiter.limit("10 per hour")
def send_completion_email(request_id):
    if s3_client is None:
        return jsonify({"error": "MinIO is not configured"}), 500

    if not request_id:
        return jsonify({"error": "Request ID is required"}), 400

    app.logger.info(f"Received request to send completion email for ID: {request_id}")

    # Fetch request details from DB
    request_data = database.get_request_by_id(request_id)
    if not request_data:
        app.logger.error(f"Request ID not found: {request_id}")
        return jsonify({"error": "Request not found"}), 404

    # Validate request status and data
    recipient_email = request_data.get('email')
    relative_edited_path = request_data.get('edited_image_path')
    status = request_data.get('status')

    if status != 'pending_email':
        app.logger.warning(f"Attempt to send email for non-completed request ID: {request_id} (Status: {status})")
        return jsonify({"error": f"Request status is '{status}', not 'completed'. Cannot send email yet."}), 400
    if not recipient_email or not relative_edited_path:
        app.logger.error(f"Missing email or edited image path for request ID: {request_id}")
        return jsonify({"error": "Recipient email or edited image path missing"}), 400

    # Fetch the image from MinIO
    try:
        response = s3_client.get_object(Bucket=MINIO_BUCKET_NAME, Key=relative_edited_path)
        file_data = response['Body'].read()
        content_type = response['ContentType']
        filename = os.path.basename(relative_edited_path)
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            app.logger.error(f"Edited image not found in MinIO: {relative_edited_path}")
            return jsonify({"error": "Edited image not found in storage"}), 404
        app.logger.error(f"Error retrieving edited image from MinIO: {e}")
        return jsonify({"error": "Internal server error"}), 500

    # Prepare Email
    subject = "Your AI Image Edit is Ready!"
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

    # Attach the image
    msg.attach(filename=filename, content_type=content_type, data=file_data)
    app.logger.info(f"Attached file '{filename}' with type '{content_type}' to email for {recipient_email}.")

    # Send Email
    try:
        mail.send(msg)
        app.logger.info(f"Email sent successfully to {recipient_email} for request {request_id}.")
        if database.update_request_status(request_id, status='completed'):
            app.logger.info(f"Updated status to 'completed' for request {request_id}.")
        else:
            app.logger.warning(f"Email sent, but failed to update status for {request_id}.")
        return jsonify({"message": f"Email sent successfully to {recipient_email}"}), 200
    except Exception as e:
        app.logger.error(f"Failed to send email for request {request_id}: {e}")
        return jsonify({"error": f"Failed to send email: {e}"}), 500

@app.route('/uploads/<path:filepath>')
def serve_upload(filepath):
    if s3_client is None:
        return jsonify({"error": "MinIO is not configured"}), 500

    try:
        response = s3_client.get_object(Bucket=MINIO_BUCKET_NAME, Key=filepath)
        return Response(
            response['Body'].read(),
            mimetype=response['ContentType'],
            headers={"Content-Disposition": f"inline; filename={os.path.basename(filepath)}"}
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return jsonify({"error": "File not found"}), 404
        app.logger.error(f"Error retrieving object {filepath}: {e}")
        return jsonify({"error": "Internal server error"}), 500

# --- Main Execution ---
if __name__ == '__main__':
    print("Starting backend server...")
    database.init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)