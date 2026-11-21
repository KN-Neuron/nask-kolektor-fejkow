# Demonstrator Kolekcjonera Fejków.
# Budowa:      docker build -t kolekcjoner-fejkow .
# Uruchomienie: docker run --rm -p 8501:8501 -v "/ścieżka/do/do_udostępnienia:/data:ro" kolekcjoner-fejkow
# Indeks zbioru buduje się przy pierwszym starcie (albo przyciskiem w panelu bocznym). Dane nie są częścią obrazu.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -e .

ENV FEJKI_DATA=/data \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8501

# Przy pierwszym uruchomieniu zbuduj indeks z zamontowanego zbioru (jeśli jest), potem uruchom interfejs.
CMD ["sh", "-c", "[ -f artifacts/demo/index.json ] || [ ! -d /data ] || fejki demo build /data; streamlit run src/fejki/app/demo_app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true"]
