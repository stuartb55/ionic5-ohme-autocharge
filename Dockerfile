FROM python:3.14-slim

# Don't write .pyc files (the app dir is root-owned and the process runs as a
# non-root user) and keep stdout/stderr unbuffered for prompt container logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Build-time git SHA, surfaced at runtime via /api/version so the dashboard can
# show which build is deployed. CI passes --build-arg GIT_SHA=${{ github.sha }}.
ARG GIT_SHA=""
ENV APP_VERSION=$GIT_SHA

WORKDIR /app

# Create a non-root user to run the service.
RUN useradd --create-home --uid 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY *.py ./
COPY alembic ./alembic

# Writable directory for runtime-adjustable settings (e.g. the charge target).
# Owned by the runtime user; mount a volume here to persist across restarts.
RUN mkdir -p /app/data && chown appuser:appuser /app/data
VOLUME ["/app/data"]

USER appuser

EXPOSE 8000

# Liveness probe against the API's health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"]

# Serve the API; the app also runs the plug-in detection poll loop on startup.
# (For the headless CLI behaviour use: python main.py  /  python main.py --once)
#
# MUST stay a single worker: the app keeps its state in-process (state.store,
# the poll loop, the Ohme client, the statistics cache). Multiple workers would
# each run their own poll loop — duplicate Ohme logins, duplicate DB writes,
# and dashboards reading whichever worker answered. Never add --workers.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
