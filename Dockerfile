FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for spaCy and other tools
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_sm

# Copy application code
COPY app/ ./app/

# Create data directory for SQLite
RUN mkdir -p ./data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
