import os
import uuid
import mimetypes
from flask import Flask, request, jsonify, current_app 
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail, Message
from dotenv import load_dotenv
import logging
import boto3
from botocore.exceptions import ClientError
import click

# --- Project Specific Imports ---
import database

# --- Load Environment Variables ---
load_dotenv() # Load variables from .env file

# --- Configuration ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

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
    print("\n*** WARNING: MAIL_USERNAME or MAIL_PASSWORD not found. Email sending will likely fail. ***\n")

mail = Mail(app)

# --- MinIO/S3 Configuration ---
MINIO_ENDPOINT_URL = os.getenv('MINIO_ENDPOINT_URL') # e.g., http://minio:9000
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY')
MINIO_BUCKET_NAME = os.getenv('MINIO_BUCKET_NAME')

s3_client = None
if all([MINIO_ENDPOINT_URL, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET_NAME]):
    try:
        app.logger.info(f"Attempting to connect to MinIO at {MINIO_ENDPOINT_URL}...")
        # Note: For MinIO, often helpful to explicitly set signature version
        # and potentially disable SSL verification if using http internally
        s3_client = boto3.client(
            's3',
            endpoint_url=MINIO_ENDPOINT_URL,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=boto3.session.Config(signature_version='s3v4'), # Good practice for MinIO
            # verify=False # Uncomment if using HTTP and facing SSL issues (less secure)
        )
        # Verify connection by trying to list buckets (optional)
        # s3_client.list_buckets()
        app.logger.info(f"Successfully initialized S3 client for MinIO bucket '{MINIO_BUCKET_NAME}'.")

        # --- Ensure Bucket Exists ---
        try:
            s3_client.head_bucket(Bucket=MINIO_BUCKET_NAME)
            app.logger.info(f"Bucket '{MINIO_BUCKET_NAME}' already exists.")
        except ClientError as e:
            # If a 404 error, the bucket doesn't exist
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                app.logger.info(f"Bucket '{MINIO_BUCKET_NAME}' does not exist. Creating...")
                # Specify region for AWS S3 compatibility if needed, often ignored by MinIO
                # s3_client.create_bucket(Bucket=MINIO_BUCKET_NAME, CreateBucketConfiguration={'LocationConstraint': 'us-east-1'})
                s3_client.create_bucket(Bucket=MINIO_BUCKET_NAME)
                app.logger.info(f"Bucket '{MINIO_BUCKET_NAME}' created successfully.")
            else:
                app.logger.error(f"Error checking for bucket {MINIO_BUCKET_NAME}: {e}")
                s3_client = None # Disable client if we can't verify/create bucket

    except Exception as e:
        app.logger.error(f"Failed to initialize S3 client: {e}")
        s3_client = None # Ensure client is None if setup fails
else:
    print("\n*** WARNING: MinIO environment variables (URL, KEY, SECRET, BUCKET) not fully set. S3 functionality disabled. ***\n")


# --- Rate Limiting ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour", "5 per minute"]
)

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Flask CLI Command ---
@app.cli.command('init-db')
def init_db_command():
    """Initialize the database (Create tables)."""
    try:
        click.echo('Attempting to initialize the database...')
        database.init_db()
        click.echo('Database initialization check completed successfully.')
    except Exception as e:
        click.echo(f'Error initializing database: {e}', err=True)

# --- Routes ---
@app.route('/submit', methods=['POST'])
@limiter.limit("3 per minute")
def submit_request():
    if not s3_client:
        return jsonify({"error": "Storage service not configured"}), 503 # Service Unavailable

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

    request_id = str(uuid.uuid4())
    image_ext = image_file.filename.rsplit('.', 1)[1].lower()
    proof_ext = proof_file.filename.rsplit('.', 1)[1].lower()

    # Define Object Keys (filenames within MinIO bucket)
    image_filename_base = secure_filename(f"{request_id}_original.{image_ext}")
    proof_filename_base = secure_filename(f"{request_id}_proof.{proof_ext}")
    image_object_key = f"original/{image_filename_base}"
    proof_object_key = f"proof/{proof_filename_base}"

    uploaded_keys = [] # Keep track of what was successfully uploaded for potential cleanup

    try:
        # Upload Original Image
        app.logger.info(f"Uploading original image to S3: {MINIO_BUCKET_NAME}/{image_object_key}")
        image_content_type = image_file.content_type or mimetypes.guess_type(image_filename_base)[0] or 'application/octet-stream'
        s3_client.upload_fileobj(
            image_file,
            MINIO_BUCKET_NAME,
            image_object_key,
            ExtraArgs={'ContentType': image_content_type}
        )
        uploaded_keys.append(image_object_key)
        app.logger.info(f"Successfully uploaded {image_object_key}")

        # Upload Proof Image
        app.logger.info(f"Uploading proof image to S3: {MINIO_BUCKET_NAME}/{proof_object_key}")
        proof_content_type = proof_file.content_type or mimetypes.guess_type(proof_filename_base)[0] or 'application/octet-stream'
        s3_client.upload_fileobj(
            proof_file,
            MINIO_BUCKET_NAME,
            proof_object_key,
            ExtraArgs={'ContentType': proof_content_type}
        )
        uploaded_keys.append(proof_object_key)
        app.logger.info(f"Successfully uploaded {proof_object_key}")

        # Store Object Keys in Database
        database.add_request(request_id, email, description, image_object_key, proof_object_key)
        app.logger.info(f"Request {request_id} added to database with S3 object keys.")

        return jsonify({"message": "Request received successfully", "request_id": request_id}), 201

    except ClientError as e:
        app.logger.error(f"S3 Upload Error for request {request_id}: {e}")
        # Attempt to clean up already uploaded files if error occurred mid-way
        if uploaded_keys:
            app.logger.warning(f"Attempting S3 cleanup for request {request_id} due to error...")
            for key in uploaded_keys:
                try:
                    s3_client.delete_object(Bucket=MINIO_BUCKET_NAME, Key=key)
                    app.logger.info(f"Cleaned up S3 object: {key}")
                except ClientError as delete_e:
                    app.logger.error(f"Failed to cleanup S3 object {key}: {delete_e}")
        return jsonify({"error": "Failed to upload files to storage"}), 500
    except Exception as e:
        # Catch other potential errors (e.g., database errors after upload)
        # Basic cleanup if DB insertion fails *after* successful S3 uploads
        if uploaded_keys:
             app.logger.warning(f"Attempting S3 cleanup for request {request_id} due to non-S3 error...")
             # Implement cleanup as above
        app.logger.error(f"Error processing request {request_id}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    db_ok = False
    s3_ok = False
    details = {}

    # Check DB
    try:
        with database.get_db_connection() as (conn, cur): # Use tuple unpacking
            cur.execute("SELECT 1") # Use cursor from context
        db_ok = True
    except Exception as e:
        details['database'] = str(e)
        app.logger.error(f"Health check DB failed: {e}")

    # Check S3 (if configured)
    if s3_client:
        try:
            s3_client.head_bucket(Bucket=MINIO_BUCKET_NAME)
            s3_ok = True
        except ClientError as e:
            details['s3'] = str(e.response['Error'])
            app.logger.error(f"Health check S3 failed: {e}")
        except Exception as e: # Catch other boto3/connection errors
            details['s3'] = str(e)
            app.logger.error(f"Health check S3 failed: {e}")
    else:
        details['s3'] = "Client not configured" # Indicate S3 isn't expected to work

    if db_ok and (s3_ok or not s3_client): # S3 check only matters if configured
         return jsonify({"status": "ok", "checks": {"database": db_ok, "s3": s3_ok if s3_client else "not configured"}}), 200
    else:
        return jsonify({"status": "error", "details": details, "checks": {"database": db_ok, "s3": s3_ok if s3_client else "not configured"}}), 500


@app.route('/send_completion_email/<string:request_id>', methods=['POST'])
def send_completion_email(request_id):
    if not s3_client:
        return jsonify({"error": "Storage service not configured"}), 503

    if not request_id:
        return jsonify({"error": "Request ID is required"}), 400

    app.logger.info(f"Received request to send completion email for ID: {request_id}")

    request_data = database.get_request_by_id(request_id)

    if not request_data:
        app.logger.error(f"Request ID not found: {request_id}")
        return jsonify({"error": "Request not found"}), 404

    recipient_email = request_data.get('email')
    # This path is now an S3 Object Key
    edited_object_key = request_data.get('edited_image_path')
    status = request_data.get('status')

    if status != 'pending_email':
         app.logger.warning(f"Attempt to send email for non-completed request ID: {request_id} (Status: {status})")
         return jsonify({"error": f"Request status is '{status}', not 'pending_email'. Cannot send email yet."}), 400
    if not recipient_email:
         app.logger.error(f"Missing recipient email for request ID: {request_id}")
         return jsonify({"error": "Recipient email missing for this request"}), 400
    if not edited_object_key:
        app.logger.error(f"Missing edited image object key for request ID: {request_id}")
        return jsonify({"error": "Edited image path missing for this request"}), 400

    # Prepare Email (before fetching S3 object to save API calls if basic validation fails)
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

    # Fetch image from S3 and attach
    try:
        app.logger.info(f"Fetching edited image from S3: {MINIO_BUCKET_NAME}/{edited_object_key}")
        s3_response = s3_client.get_object(Bucket=MINIO_BUCKET_NAME, Key=edited_object_key)

        file_data = s3_response['Body'].read()
        content_type = s3_response.get('ContentType', 'application/octet-stream')
        # Extract filename from the object key for the attachment
        filename = edited_object_key.split('/')[-1]

        msg.attach(filename=filename, content_type=content_type, data=file_data)
        app.logger.info(f"Attached file '{filename}' (from S3) with type '{content_type}' to email for {recipient_email}.")

    except ClientError as e:
        app.logger.error(f"Error fetching S3 object {edited_object_key} for request {request_id}: {e}")
        # Check if the error is "NoSuchKey" (404)
        if e.response['Error']['Code'] == 'NoSuchKey':
            return jsonify({"error": "Edited image not found in storage"}), 404
        else:
            return jsonify({"error": f"Failed to retrieve image file from storage: {e.response['Error']['Message']}"}), 500
    except Exception as e:
        app.logger.error(f"Error attaching file from S3 {edited_object_key} for request {request_id}: {e}")
        return jsonify({"error": f"Failed to process image file from storage: {e}"}), 500

    # Send Email
    try:
        app.logger.info(f"Attempting to send email via {app.config['MAIL_SERVER']} to {recipient_email} for request {request_id}...")
        mail.send(msg)
        app.logger.info(f"Email sent successfully to {recipient_email} for request {request_id}.")

        # Update DB status to 'completed' AFTER sending
        if database.update_request_status(request_id, status='completed', edited_path=edited_object_key): # Pass key just in case update logic needs it
             app.logger.info(f"Successfully updated status to 'completed' for request {request_id} after sending email.")
        else:
             app.logger.warning(f"Email sent for {request_id}, but failed to update status to 'completed' in DB.")

        return jsonify({"message": f"Email sent successfully to {recipient_email}"}), 200

    except Exception as e:
        app.logger.error(f"Failed to send email for request {request_id} to {recipient_email}: {e}")
        # Note: We might have fetched from S3 but failed to send mail. No S3 cleanup needed here.
        return jsonify({"error": f"Failed to send email. Check server logs for details. Error: {e}"}), 500


# --- NEW: Endpoint to get a temporary URL for an image ---
# TODO: Add proper authentication/authorization to this endpoint!
@app.route('/get_image_url/<string:request_id>/<string:image_type>', methods=['GET'])
def get_image_url(request_id, image_type):
    if not s3_client:
        return jsonify({"error": "Storage service not configured"}), 503

    if image_type not in ['original', 'proof', 'edited']:
        return jsonify({"error": "Invalid image type specified"}), 400

    request_data = database.get_request_by_id(request_id)
    if not request_data:
        return jsonify({"error": "Request not found"}), 404

    object_key = None
    if image_type == 'original':
        object_key = request_data.get('original_image_path')
    elif image_type == 'proof':
        object_key = request_data.get('payment_proof_path')
    elif image_type == 'edited':
        object_key = request_data.get('edited_image_path')

    if not object_key:
        return jsonify({"error": f"{image_type.capitalize()} image path not found for this request"}), 404

    try:
        # Generate a pre-signed URL valid for 1 hour (3600 seconds)
        # IMPORTANT: Ensure your MinIO server is accessible from where the URL will be used (e.g., user's browser).
        # Boto3 uses the `endpoint_url` from its config by default. If this is internal (`http://minio:9000`),
        # the generated URL might not work externally. You might need to configure boto3 differently
        # or use a reverse proxy to make MinIO accessible on a public URL and configure that here.
        # Alternatively, set MINIO_PUBLIC_URL_BASE and construct URL if bucket is public.
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': MINIO_BUCKET_NAME, 'Key': object_key},
            ExpiresIn=3600  # URL expires in 1 hour
        )
        app.logger.info(f"Generated pre-signed URL for {object_key}")
        return jsonify({"url": url})

    except ClientError as e:
        app.logger.error(f"Could not generate pre-signed URL for {object_key}: {e}")
        return jsonify({"error": "Could not generate image URL"}), 500
    except Exception as e:
         app.logger.error(f"Unexpected error generating pre-signed URL for {object_key}: {e}")
         return jsonify({"error": "Internal server error generating URL"}), 500


# --- Main Execution ---
if __name__ == '__main__':
    print("Starting backend server with MinIO integration...")
    # database.init_db() is called within database.py when imported
    # Remove setup_directories() call
    app.run(host='0.0.0.0', port=5000, debug=True) # Use debug=False for production