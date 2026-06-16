#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/job_hunt_prod_env.sh"

aws s3api head-bucket --bucket "${S3_UPLOAD_BUCKET}" 2>/dev/null && {
  echo "S3 bucket already exists: ${S3_UPLOAD_BUCKET}"
  exit 0
}

aws s3api create-bucket \
  --bucket "${S3_UPLOAD_BUCKET}" \
  --region "${AWS_REGION}"

aws s3api put-public-access-block \
  --bucket "${S3_UPLOAD_BUCKET}" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-versioning \
  --bucket "${S3_UPLOAD_BUCKET}" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "${S3_UPLOAD_BUCKET}" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

echo "Created private encrypted S3 bucket: ${S3_UPLOAD_BUCKET}"
