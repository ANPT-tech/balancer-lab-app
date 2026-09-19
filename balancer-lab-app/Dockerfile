FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Intentionally plain HTTP. TLS/SSL must be terminated by Apache/Nginx.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
