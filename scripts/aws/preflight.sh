#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/job_hunt_prod_env.sh"

command -v aws >/dev/null || { echo "aws CLI is required."; exit 1; }
command -v eb >/dev/null || { echo "Elastic Beanstalk CLI is required."; exit 1; }

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
if [[ "${ACCOUNT_ID}" != "${AWS_ACCOUNT_ID}" ]]; then
  echo "Expected AWS account ${AWS_ACCOUNT_ID}, but current CLI is authenticated to ${ACCOUNT_ID}."
  exit 1
fi

aws configure get region >/dev/null || aws configure set region "${AWS_REGION}"

echo "AWS account: ${ACCOUNT_ID}"
echo "AWS region: ${AWS_REGION}"
echo "EB application: ${EB_APPLICATION_NAME}"
echo "EB environment: ${EB_ENVIRONMENT_NAME}"
echo "RDS identifier: ${RDS_IDENTIFIER}"
echo "S3 upload bucket: ${S3_UPLOAD_BUCKET}"
