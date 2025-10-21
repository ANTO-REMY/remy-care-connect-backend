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
    pip install psycopg2-binary && \
    pip install -r requirements.txt

# Copy project files
COPY . .

# Change ownership of the application files to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5000

# Run the Flask app
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
