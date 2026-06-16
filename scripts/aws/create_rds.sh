#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/job_hunt_prod_env.sh"

if [[ -z "${RDS_MASTER_PASSWORD:-}" ]]; then
  echo "Set RDS_MASTER_PASSWORD before running this script."
  exit 1
fi

if aws rds describe-db-instances --db-instance-identifier "${RDS_IDENTIFIER}" >/dev/null 2>&1; then
  echo "RDS instance already exists: ${RDS_IDENTIFIER}"
  exit 0
fi

aws rds create-db-instance \
  --db-instance-identifier "${RDS_IDENTIFIER}" \
  --db-instance-class "${RDS_INSTANCE_CLASS}" \
  --engine postgres \
  --allocated-storage "${RDS_ALLOCATED_STORAGE}" \
  --db-name "${RDS_DB_NAME}" \
  --master-username "${RDS_MASTER_USERNAME}" \
  --master-user-password "${RDS_MASTER_PASSWORD}" \
  --backup-retention-period 7 \
  --storage-encrypted \
  --no-publicly-accessible \
  --region "${AWS_REGION}"

echo "Creating RDS PostgreSQL instance: ${RDS_IDENTIFIER}"
echo "Wait with: aws rds wait db-instance-available --db-instance-identifier ${RDS_IDENTIFIER} --region ${AWS_REGION}"
