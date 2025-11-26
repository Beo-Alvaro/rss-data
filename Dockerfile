# Start from a small, supported Python image
FROM python:3.11-slim

# Ensure Python output is unbuffered (logs show up promptly)
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-root user for safety
RUN groupadd -r app && useradd -r -g app app || true

# Copy source
COPY . /app

# Create data dir and set ownership
RUN mkdir -p /app/data && chown -R app:app /app

USER app

# Default command: run the RSS fetcher as a long-running worker
# You can override args in Render service settings if desired
ENTRYPOINT ["python", "scripts/rss_fetcher.py", "--interval", "300", "--db", "data/rss_items.db"]
