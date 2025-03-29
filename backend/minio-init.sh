#!/bin/sh
# minio-init.sh - Ensure Predefined User/Policy

set -eu

# Check for mandatory environment variables
: "${MINIO_BUCKET_NAME:?MINIO_BUCKET_NAME is required}"
: "${MINIO_ACCESS_KEY:?MINIO_ACCESS_KEY is required}"
: "${MINIO_SECRET_KEY:?MINIO_SECRET_KEY is required}"

# Variables from environment
MINIO_ENDPOINT_HOST="${MINIO_ENDPOINT_HOST:-minio}"
MINIO_ENDPOINT_PORT="${MINIO_ENDPOINT_PORT:-9000}"

# Use root creds for admin tasks
MINIO_ADMIN_ACCESS_KEY="${MINIO_ADMIN_ACCESS_KEY:-$MINIO_ROOT_USER}"
MINIO_ADMIN_SECRET_KEY="${MINIO_ADMIN_SECRET_KEY:-$MINIO_ROOT_PASSWORD}"

TARGET_BUCKET="${MINIO_BUCKET_NAME}"

# Application's predefined credentials
APP_ACCESS_KEY="${MINIO_ACCESS_KEY}"
APP_SECRET_KEY="${MINIO_SECRET_KEY}"

echo "Waiting for MinIO server at ${MINIO_ENDPOINT_HOST}:${MINIO_ENDPOINT_PORT}..."

# Wait for MinIO to be available and configure alias using admin credentials
attempts=0
max_attempts=30
delay=3
until mc alias set myminio "http://${MINIO_ENDPOINT_HOST}:${MINIO_ENDPOINT_PORT}" "${MINIO_ADMIN_ACCESS_KEY}" "${MINIO_ADMIN_SECRET_KEY}"; do
  attempts=$((attempts + 1))
  if [ "$attempts" -ge "$max_attempts" ]; then
    echo "Error: MinIO server did not become ready after $((max_attempts * delay)) seconds."
    exit 1
  fi
  echo "MinIO not ready (attempt ${attempts}/${max_attempts})..."
  sleep "$delay"
done

echo "MinIO server is ready. Ensuring configuration..."

# Create bucket if it doesn't exist
if ! mc ls myminio/"${TARGET_BUCKET}" > /dev/null 2>&1; then
  echo "Creating bucket '${TARGET_BUCKET}'..."
  mc mb myminio/"${TARGET_BUCKET}"
else
  echo "Bucket '${TARGET_BUCKET}' already exists."
fi

# Ensure the application user exists
if ! mc admin user info myminio "${APP_ACCESS_KEY}" > /dev/null 2>&1; then
  echo "Creating application user '${APP_ACCESS_KEY}'..."
  mc admin user add myminio "${APP_ACCESS_KEY}" "${APP_SECRET_KEY}"
else
  echo "Application user '${APP_ACCESS_KEY}' already exists."
  # Uncomment the following line to update the user's password if needed:
  # mc admin user update --password "${APP_SECRET_KEY}" myminio "${APP_ACCESS_KEY}"
fi

# Define and ensure the bucket-specific policy
POLICY_NAME="app-policy-${TARGET_BUCKET}"
POLICY_FILE="/tmp/policy-${TARGET_BUCKET}-policy.json"

cat <<EOF > "${POLICY_FILE}"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:HeadBucket"
      ],
      "Resource": [
        "arn:aws:s3:::${TARGET_BUCKET}/*",
        "arn:aws:s3:::${TARGET_BUCKET}"
      ]
    }
  ]
}
EOF

echo "Creating/updating policy '${POLICY_NAME}'..."
mc admin policy create myminio "${POLICY_NAME}" "${POLICY_FILE}"
if [ $? -ne 0 ]; then
  echo "Failed to create policy '${POLICY_NAME}'. It may already exist or there was an error."
else
  echo "Policy '${POLICY_NAME}' created successfully."
fi

echo "Attaching policy '${POLICY_NAME}' to user '${APP_ACCESS_KEY}'..."
mc admin policy attach myminio "${POLICY_NAME}" --user "${APP_ACCESS_KEY}"

# Clean up the temporary policy file
rm -f "${POLICY_FILE}"

echo "MinIO configuration complete for predefined user."
exit 0
