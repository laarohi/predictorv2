FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from the pinned lock for reproducible images,
# then the app package itself without re-resolving its deps. Regenerate the
# lock after changing pyproject.toml with:
#   docker run --rm <image> pip freeze > backend/requirements.lock.txt
COPY pyproject.toml requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt \
    && pip install --no-cache-dir --no-deps -e .

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
