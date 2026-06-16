#!/usr/bin/env bash
set -euo pipefail

export AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-453732174568}"
export AWS_REGION="${AWS_REGION:-us-east-1}"

export EB_APPLICATION_NAME="${EB_APPLICATION_NAME:-job-hunt-agent}"
export EB_ENVIRONMENT_NAME="${EB_ENVIRONMENT_NAME:-job-hunt-agent-prod}"
export EB_PLATFORM="${EB_PLATFORM:-python-3.12}"

export RDS_IDENTIFIER="${RDS_IDENTIFIER:-job-hunt-agent-prod-db}"
export RDS_DB_NAME="${RDS_DB_NAME:-job_hunt_agent}"
export RDS_MASTER_USERNAME="${RDS_MASTER_USERNAME:-job_agent_user}"
export RDS_INSTANCE_CLASS="${RDS_INSTANCE_CLASS:-db.t4g.micro}"
export RDS_ALLOCATED_STORAGE="${RDS_ALLOCATED_STORAGE:-20}"

export S3_UPLOAD_BUCKET="${S3_UPLOAD_BUCKET:-job-hunt-agent-prod-uploads-${AWS_ACCOUNT_ID}-${AWS_REGION}}"

export EB_INSTANCE_TYPE="${EB_INSTANCE_TYPE:-t3.micro}"
export EB_SERVICE_ROLE="${EB_SERVICE_ROLE:-aws-elasticbeanstalk-service-role}"
export EB_EC2_ROLE="${EB_EC2_ROLE:-aws-elasticbeanstalk-ec2-role}"

export JOB_AGENT_COOKIE_SECURE="${JOB_AGENT_COOKIE_SECURE:-true}"
export JOB_AGENT_DEV_RETURN_OTP="${JOB_AGENT_DEV_RETURN_OTP:-false}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"

if [[ -d "/opt/homebrew/opt/expat/lib" ]]; then
  export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:${DYLD_LIBRARY_PATH:-}"
fi
