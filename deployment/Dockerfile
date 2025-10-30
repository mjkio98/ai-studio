# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Install system dependencies including browser support for Crawl4AI
RUN apt-get update && apt-get install -y \
    gcc \
    # Browser dependencies for Crawl4AI
    wget \
    gnupg \
    unzip \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgtk-3-0 \
    libgtk-4-1 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    # Chromium browser
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set browser environment variables for Crawl4AI
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_PATH=/usr/bin/chromium
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV GOOGLE_CHROME_BIN=/usr/bin/chromium

# Copy requirements first for better Docker caching
COPY config/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers for Crawl4AI
RUN python -m playwright install chromium
RUN python -m playwright install-deps chromium

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose port
EXPOSE 8080

# Use gunicorn for production with extended timeout for transcript processing
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "240", "--graceful-timeout", "240", "app:app"]