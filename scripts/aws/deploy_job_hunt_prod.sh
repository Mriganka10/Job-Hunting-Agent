#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/preflight.sh"
"${SCRIPT_DIR}/create_storage.sh"
"${SCRIPT_DIR}/create_rds.sh"

source "${SCRIPT_DIR}/job_hunt_prod_env.sh"
aws rds wait db-instance-available --db-instance-identifier "${RDS_IDENTIFIER}" --region "${AWS_REGION}"

RDS_ENDPOINT="$(aws rds describe-db-instances \
  --db-instance-identifier "${RDS_IDENTIFIER}" \
  --region "${AWS_REGION}" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)"

export JOB_AGENT_DATABASE_URL="postgresql://${RDS_MASTER_USERNAME}:${RDS_MASTER_PASSWORD}@${RDS_ENDPOINT}:5432/${RDS_DB_NAME}"

"${SCRIPT_DIR}/deploy_elastic_beanstalk.sh"
