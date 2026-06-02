FROM python:3.12-slim

WORKDIR /app

# Create a non-root user to run the service.
RUN useradd --create-home --uid 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY *.py ./

USER appuser

EXPOSE 8000

# Liveness probe against the API's health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"]

# Serve the API; the app also runs the plug-in detection poll loop on startup.
# (For the headless CLI behaviour use: python main.py  /  python main.py --once)
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
