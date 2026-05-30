FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY config.py bluelink.py ohme_client.py main.py ./

CMD ["python", "-u", "main.py"]
