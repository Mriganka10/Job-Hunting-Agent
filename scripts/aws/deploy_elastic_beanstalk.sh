#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/job_hunt_prod_env.sh"

if [[ -z "${JOB_AGENT_SECRET_KEY:-}" ]]; then
  echo "Set JOB_AGENT_SECRET_KEY before deploying."
  exit 1
fi

if [[ -z "${JOB_AGENT_DATABASE_URL:-}" ]]; then
  echo "Set JOB_AGENT_DATABASE_URL before deploying."
  exit 1
fi

if [[ -z "${JOB_AGENT_SMTP_HOST:-}" || -z "${JOB_AGENT_SMTP_USERNAME:-}" || -z "${JOB_AGENT_SMTP_PASSWORD:-}" || -z "${JOB_AGENT_SMTP_FROM:-}" ]]; then
  echo "Set JOB_AGENT_SMTP_HOST, JOB_AGENT_SMTP_USERNAME, JOB_AGENT_SMTP_PASSWORD, and JOB_AGENT_SMTP_FROM before deploying."
  exit 1
fi

cd "${REPO_ROOT}"

if [[ ! -d ".elasticbeanstalk" ]]; then
  eb init "${EB_APPLICATION_NAME}" --platform "${EB_PLATFORM}" --region "${AWS_REGION}"
fi

if ! eb status "${EB_ENVIRONMENT_NAME}" >/dev/null 2>&1; then
  eb create "${EB_ENVIRONMENT_NAME}" \
    --instance_type "${EB_INSTANCE_TYPE}" \
    --service-role "${EB_SERVICE_ROLE}" \
    --instance_profile "${EB_EC2_ROLE}" \
    --single
fi

eb setenv \
  HOST="${HOST}" \
  PORT="${PORT}" \
  JOB_AGENT_SECRET_KEY="${JOB_AGENT_SECRET_KEY}" \
  JOB_AGENT_DATABASE_URL="${JOB_AGENT_DATABASE_URL}" \
  JOB_AGENT_COOKIE_SECURE="${JOB_AGENT_COOKIE_SECURE}" \
  JOB_AGENT_DEV_RETURN_OTP="${JOB_AGENT_DEV_RETURN_OTP}" \
  JOB_AGENT_SMTP_HOST="${JOB_AGENT_SMTP_HOST}" \
  JOB_AGENT_SMTP_PORT="${JOB_AGENT_SMTP_PORT:-587}" \
  JOB_AGENT_SMTP_USERNAME="${JOB_AGENT_SMTP_USERNAME}" \
  JOB_AGENT_SMTP_PASSWORD="${JOB_AGENT_SMTP_PASSWORD}" \
  JOB_AGENT_SMTP_FROM="${JOB_AGENT_SMTP_FROM}" \
  AWS_REGION="${AWS_REGION}" \
  S3_UPLOAD_BUCKET="${S3_UPLOAD_BUCKET}"

eb deploy "${EB_ENVIRONMENT_NAME}"
eb status "${EB_ENVIRONMENT_NAME}"
