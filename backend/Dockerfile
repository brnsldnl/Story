FROM python:3.12-slim

# FreeTDS: Logo MSSQL'e salt okunur bağlantı için
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        unixodbc tdsodbc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app ./app

RUN useradd --system --create-home pdks \
    && mkdir -p /var/lib/pdks/photos \
    && chown -R pdks:pdks /var/lib/pdks
USER pdks

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
