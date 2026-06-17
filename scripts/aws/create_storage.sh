#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/job_hunt_prod_env.sh"

if aws s3api head-bucket --bucket "${S3_UPLOAD_BUCKET}" 2>/dev/null; then
  echo "S3 bucket already exists: ${S3_UPLOAD_BUCKET}"
else
  aws s3api create-bucket \
    --bucket "${S3_UPLOAD_BUCKET}" \
    --region "${AWS_REGION}"
fi

aws s3api put-public-access-block \
  --bucket "${S3_UPLOAD_BUCKET}" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-versioning \
  --bucket "${S3_UPLOAD_BUCKET}" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "${S3_UPLOAD_BUCKET}" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

POLICY_DOCUMENT="$(mktemp)"
cat > "${POLICY_DOCUMENT}" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::${S3_UPLOAD_BUCKET}/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::${S3_UPLOAD_BUCKET}"
    }
  ]
}
JSON

aws iam put-role-policy \
  --role-name "${EB_EC2_ROLE}" \
  --policy-name JobHuntAgentS3ObjectAccess \
  --policy-document "file://${POLICY_DOCUMENT}"

rm -f "${POLICY_DOCUMENT}"

echo "Private encrypted S3 bucket is ready: ${S3_UPLOAD_BUCKET}"
echo "Attached S3 object access policy to EC2 role: ${EB_EC2_ROLE}"
