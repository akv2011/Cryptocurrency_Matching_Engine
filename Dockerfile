FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Make sure src/ is importable as a package
ENV PYTHONPATH=/app

# Default port (overridden at runtime by Render via the PORT env var)
ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "src.main"]
