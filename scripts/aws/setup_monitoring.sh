#!/usr/bin/env bash
# Production alerts for the Job Hunting Agent (CloudWatch + SNS + SQS DLQ).
#
# The app writes CloudWatch Embedded Metric Format (EMF) log lines, so the
# metrics below appear automatically in the "JobHuntingAgent" namespace once
# the ECS tasks log to CloudWatch (awslogs driver). This script only creates
# the alert topic, the alarms and the queue's dead-letter redrive policy.
# It is idempotent: re-running updates the same alarms.
#
# Required:
#   AWS_REGION              e.g. ap-south-1
#   ALERT_EMAIL             who receives alerts (confirm the SNS e-mail once)
# Optional:
#   JOB_AGENT_QUEUE_URL     scheduled-run queue; adds the DLQ redrive policy
#   JOB_AGENT_DLQ_ARN       dead-letter queue ARN (required with the queue URL)
#   JOB_AGENT_DLQ_NAME      dead-letter queue name, for the DLQ alarm
#   LLM_DAILY_BUDGET_USD    default 5
#   ALB_ARN_SUFFIX          e.g. app/shared-alb/123abc, adds an ALB 5xx-rate alarm
#   SOURCES                 job sources to watch (space separated)
set -euo pipefail

: "${AWS_REGION:?Set AWS_REGION}"
: "${ALERT_EMAIL:?Set ALERT_EMAIL}"
NAMESPACE="${JOB_AGENT_METRICS_NAMESPACE:-JobHuntingAgent}"
PREFIX="${ALARM_PREFIX:-job-hunting-agent}"
LLM_DAILY_BUDGET_USD="${LLM_DAILY_BUDGET_USD:-5}"
SOURCES="${SOURCES:-linkedin naukri himalayas remotive arbeitnow jobicy remoteok adzuna careerjet jooble jsearch}"
MAX_RECEIVES="${JOB_AGENT_QUEUE_MAX_RECEIVES:-3}"

TOPIC_ARN=$(aws sns create-topic --region "$AWS_REGION" --name "${PREFIX}-alerts" --query TopicArn --output text)
aws sns subscribe --region "$AWS_REGION" --topic-arn "$TOPIC_ARN" --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
echo "Alerts go to $TOPIC_ARN (confirm the subscription e-mail sent to $ALERT_EMAIL)."

alarm() {
  # alarm NAME DESCRIPTION EVENT METRIC STAT THRESHOLD PERIOD EVAL [OPERATOR] [EXTRA_DIMENSION]
  local name="$1" description="$2" event="$3" metric="$4" stat="$5" threshold="$6" period="$7" evaluations="$8"
  local operator="${9:-GreaterThanThreshold}" extra="${10:-}"
  local dims="Name=Event,Value=${event}"
  [[ -n "$extra" ]] && dims="${dims} ${extra}"
  local stat_args=(--statistic "$stat")
  [[ "$stat" == p* ]] && stat_args=(--extended-statistic "$stat")
  # shellcheck disable=SC2086
  aws cloudwatch put-metric-alarm --region "$AWS_REGION" \
    --alarm-name "${PREFIX}-${name}" --alarm-description "$description" \
    --namespace "$NAMESPACE" --metric-name "$metric" --dimensions $dims \
    "${stat_args[@]}" --period "$period" --evaluation-periods "$evaluations" \
    --threshold "$threshold" --comparison-operator "$operator" \
    --treat-missing-data notBreaching --alarm-actions "$TOPIC_ARN" --ok-actions "$TOPIC_ARN"
  echo "alarm ${PREFIX}-${name}"
}

# Operations ------------------------------------------------------------------
alarm run-p95-slow "Agent run p95 above 60 s for 15 minutes" run_completed duration_s p95 60 300 3
alarm runs-failing "3+ agent runs failed in an hour" run_failed duration_s SampleCount 2 3600 1
alarm scheduled-run-failed "A scheduled run failed after all retries" scheduled_run_failed final_failure Sum 0 3600 1
alarm server-errors "10+ HTTP 5xx responses in 10 minutes" http_5xx latency_ms SampleCount 9 600 1
alarm approval-send-failed "A recruiter email approved by a user failed to send" approval_send_failed count Sum 0 3600 1

# AI cost ------------------------------------------------------------------------
alarm llm-daily-spend "LLM spend above the daily budget" llm_call cost_usd Sum "$LLM_DAILY_BUDGET_USD" 86400 1

# Recommendation quality: share of rated leads marked "not relevant" ---------------
alarm not-relevant-rate "More than 15% of rated leads were not relevant today" lead_feedback not_relevant Average 0.15 86400 1

# Job sources: failing in more than half of runs for an hour ----------------------
for source in $SOURCES; do
  alarm "source-${source}-failing" "Job source ${source} failing in over 50% of runs for 1 hour" source_result failed Average 0.5 3600 1 GreaterThanThreshold "Name=Source,Value=${source}"
done

# Optional: ALB 5xx rate above 1% --------------------------------------------------
if [[ -n "${ALB_ARN_SUFFIX:-}" ]]; then
  aws cloudwatch put-metric-alarm --region "$AWS_REGION" --alarm-name "${PREFIX}-alb-5xx-rate" \
    --alarm-description "ALB target 5xx above 1% of requests for 10 minutes" \
    --metrics "[
      {\"Id\":\"errors\",\"MetricStat\":{\"Metric\":{\"Namespace\":\"AWS/ApplicationELB\",\"MetricName\":\"HTTPCode_Target_5XX_Count\",\"Dimensions\":[{\"Name\":\"LoadBalancer\",\"Value\":\"${ALB_ARN_SUFFIX}\"}]},\"Period\":300,\"Stat\":\"Sum\"},\"ReturnData\":false},
      {\"Id\":\"requests\",\"MetricStat\":{\"Metric\":{\"Namespace\":\"AWS/ApplicationELB\",\"MetricName\":\"RequestCount\",\"Dimensions\":[{\"Name\":\"LoadBalancer\",\"Value\":\"${ALB_ARN_SUFFIX}\"}]},\"Period\":300,\"Stat\":\"Sum\"},\"ReturnData\":false},
      {\"Id\":\"rate\",\"Expression\":\"IF(requests > 50, errors / requests, 0)\",\"Label\":\"5xx rate\",\"ReturnData\":true}
    ]" --evaluation-periods 2 --threshold 0.01 --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching --alarm-actions "$TOPIC_ARN"
  echo "alarm ${PREFIX}-alb-5xx-rate"
fi

# Scheduled-run queue: redrive failing messages to the DLQ and alarm on it ----------
if [[ -n "${JOB_AGENT_QUEUE_URL:-}" ]]; then
  : "${JOB_AGENT_DLQ_ARN:?Set JOB_AGENT_DLQ_ARN with JOB_AGENT_QUEUE_URL}"
  aws sqs set-queue-attributes --region "$AWS_REGION" --queue-url "$JOB_AGENT_QUEUE_URL" \
    --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${JOB_AGENT_DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"${MAX_RECEIVES}\\\"}\"}"
  echo "DLQ redrive after ${MAX_RECEIVES} receives -> ${JOB_AGENT_DLQ_ARN}"
fi
if [[ -n "${JOB_AGENT_DLQ_NAME:-}" ]]; then
  aws cloudwatch put-metric-alarm --region "$AWS_REGION" --alarm-name "${PREFIX}-dlq-not-empty" \
    --alarm-description "Scheduled runs are in the dead-letter queue" \
    --namespace AWS/SQS --metric-name ApproximateNumberOfMessagesVisible \
    --dimensions "Name=QueueName,Value=${JOB_AGENT_DLQ_NAME}" --statistic Maximum --period 300 \
    --evaluation-periods 1 --threshold 0 --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching --alarm-actions "$TOPIC_ARN"
  echo "alarm ${PREFIX}-dlq-not-empty"
fi

echo "Done. Dashboards: CloudWatch > Metrics > ${NAMESPACE}; in-app: /admin/metrics (JOB_AGENT_ADMIN_EMAILS)."
