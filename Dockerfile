FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JOB_AGENT_COOKIE_SECURE=true \
    JOB_AGENT_DEV_RETURN_OTP=false \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[docs]"

EXPOSE 8000

CMD ["python", "-m", "job_hunting_agent", "serve"]
