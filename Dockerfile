FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libx11-6 \
    libnss3 \
    libgconf-2-4 \
    libxrender1 \
    libxss1 \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

# Install Playwright browsers
RUN playwright install chromium

# Copy application
COPY server.py .
COPY wsgi.py .
COPY gunicorn.conf.py .
COPY templates/ templates/

# Create static directory
RUN mkdir -p static/images static/videos

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:5000/ || exit 1

# Run with gunicorn
CMD ["gunicorn", "wsgi:app", "-c", "gunicorn.conf.py"]
