FROM python:3.12-slim

WORKDIR /app

# dependencies ก่อน (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# source code
COPY . .

EXPOSE 8000

# run migrations แล้วค่อย start server
CMD ["sh", "-c", "alembic upgrade head && gunicorn app:app -k uvicorn.workers.UvicornWorker -w 1 --timeout 120 --bind 0.0.0.0:8000"]
