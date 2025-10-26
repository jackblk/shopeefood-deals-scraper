# Base image with Python
FROM python:3.13-alpine

# Install Chromium, Xvfb, fonts, bash, and utilities
RUN apk add --no-cache \
       chromium \
       xvfb \
       ttf-freefont \
       fontconfig


# Create app directory and non-root user
RUN mkdir -p /app \
    && adduser -D appuser \
    && chown -R appuser:appuser /app

USER appuser
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your scraper
COPY src/ .

COPY entrypoint.sh .

# Environment variables for Chromium
ENV CHROME_BIN=/usr/bin/chromium-browser \
    CHROME_PATH=/usr/lib/chromium/

ENV DISPLAY=:99

# ENTRYPOINT ["sh", "-c", "Xvfb :99 -screen 0 1280x720x24 & python shopeefood_scraper.py"]
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "server.py"]