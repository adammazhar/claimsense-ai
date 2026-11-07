# One image for the co-pilot API and the three mock client systems; compose picks the command.
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/adammazhar/claimsense-ai"

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src CLAIMSENSE_DATA_DIR=/app/data/synthetic

WORKDIR /app
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements-runtime.txt

COPY src ./src
COPY data/synthetic ./data/synthetic

RUN useradd --create-home --uid 1000 claimsense
USER claimsense

EXPOSE 8000
CMD ["uvicorn", "claimsense.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
