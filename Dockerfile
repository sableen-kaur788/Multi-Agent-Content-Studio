# Hugging Face Docker Space: Debian Bookworm — Tesseract + Poppler for PDF OCR.
FROM python:3.10-slim-bookworm

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN if [ -f /app/First_CrewAI/requirements-space.txt ]; then \
      pip install --upgrade pip && pip install -r /app/First_CrewAI/requirements-space.txt; \
    else \
      pip install --upgrade pip && pip install -r /app/requirements-space.txt; \
    fi

EXPOSE 7860

CMD ["sh", "-c", "if [ -f /app/First_CrewAI/streamlit_app.py ]; then cd /app/First_CrewAI; else cd /app; fi && exec streamlit run streamlit_app.py --server.port=${PORT:-7860} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
