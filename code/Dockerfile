# Demonstrator Kolekcjonera Fejków (metoda embsim: jedno wyrażenie podobieństwa, bez uczenia).
# Budowa:       docker build -t kolekcjoner-fejkow code        (albo: make docker-build)
# Uruchomienie: docker run --rm -p 8501:8501 -v "/ścieżka/do/przypadków:/data:ro" kolekcjoner-fejkow
# Model tekstu jest w obrazie, więc demo działa bez sieci. Dane organizatora nie są częścią obrazu.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Zależności w osobnej warstwie (cache). torch w wersji CPU: obraz kilka razy mniejszy.
COPY pyproject.toml ./
RUN mkdir -p src/embsim src/fejki && touch src/embsim/__init__.py src/fejki/__init__.py \
    && pip install --no-cache-dir --default-timeout=120 --retries 10 torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --default-timeout=120 --retries 10 -e .
# Model tekstu pobrany na etapie budowy (potem HF_HUB_OFFLINE=1).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
COPY src ./src
COPY config ./config
# Modele twarzy (YuNet, SFace; OpenCV Zoo, Apache-2.0, ok. 39 MB) pobrane na etapie budowy: wizerunki osób działają bez sieci.
RUN PYTHONPATH=/app/src python -m embsim.faces --download

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    EMBSIM_DATA=/data \
    EMBSIM_GALLERY=/tmp/gallery_demo.jsonl \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8501
CMD ["streamlit", "run", "src/embsim/app.py", "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless", "true"]
