FROM python:3.11.8-slim-bullseye

# Update and upgrade packages, then clean up to reduce image size
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libpq-dev \
    postgresql-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -r -u 1001 appuser

# Set working directory
WORKDIR /app/backend

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install "psycopg[binary]" && \
    pip install -r requirements.txt

# Copy project files (excluding cache files via .dockerignore)
COPY . .

# Remove any cache files that might have been copied
RUN find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
RUN find . -name "*.pyc" -delete 2>/dev/null || true

# Change ownership of the application files to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5000

# Run the Flask app with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "wsgi:app"]
