FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY alembic.ini .
COPY alembic/ alembic/

# Install
RUN pip install --no-cache-dir -e .

EXPOSE 8000
