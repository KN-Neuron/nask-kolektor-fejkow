# Demonstrator Kolekcjonera Fejków (metoda embsim: jedno wyrażenie podobieństwa, bez uczenia).
# Budowa:       docker build -t kolekcjoner-fejkow code        (albo: make docker-build)
# Uruchomienie: docker run --rm -p 8501:8501 -v "/ścieżka/do/przypadków:/data:ro" kolekcjoner-fejkow
# Model tekstu jest w obrazie, więc demo działa bez sieci. Dane organizatora nie są częścią obrazu.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Zależności w osobnych warstwach (cache). torch w wersji CPU: obraz kilka razy mniejszy. Osobna warstwa torcha: gdy pobieranie reszty
# zależności przerwie się (np. przekroczony czas odczytu z PyPI), ponowna budowa nie pobiera torcha od nowa. Pamięć podręczna pip
# (BuildKit, poza obrazem): przy słabej sieci kolejna próba bierze już pobrane pakiety zamiast pobierać wszystko od nowa.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=300 --retries 10 torch --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    mkdir -p src/embsim src/fejki && touch src/embsim/__init__.py src/fejki/__init__.py \
    && pip install --default-timeout=300 --retries 10 -e .
# Modele w obrazie, więc demo działa bez sieci (potem HF_HUB_OFFLINE=1). Gdy w kontekście budowy jest `code/models/` (lokalnie, poza
# repozytorium: model tekstu w pamięci HF `models/hf`, modele twarzy *.onnx), bierzemy je stamtąd zamiast pobierać (przy słabym łączu
# model tekstu to ok. 470 MB). W czystym klonie katalogu nie ma i oba modele są pobierane jak zwykle.
ENV HF_HOME=/app/models/hf
RUN --mount=type=bind,source=.,target=/ctx \
    mkdir -p /app/models && { [ ! -d /ctx/models ] || cp -r /ctx/models/. /app/models/; } \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
COPY src ./src
COPY config ./config
# Modele twarzy (YuNet, SFace; OpenCV Zoo, Apache-2.0, ok. 39 MB): pobierane tylko, gdy nie przyszły z `code/models/`.
RUN PYTHONPATH=/app/src python -m embsim.faces --download

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    EMBSIM_DATA=/data \
    EMBSIM_GALLERY=/tmp/gallery_demo.jsonl \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8501
CMD ["streamlit", "run", "src/embsim/app.py", "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless", "true"]
