# Multi-Agent Content Studio

**Streamlit** UI (`streamlit_app.py`): paste a **YouTube/blog URL** or **upload a PDF**, choose platform (Twitter / LinkedIn / Instagram), tone, and language (English or Hindi). The pipeline runs **extract → summarize → platform draft → tone → translate (if Hindi)**. All LLM steps use the **Groq** API (default model configurable via `GROQ_MODEL`).

**Optional:** **FastAPI** (`uvicorn app.main:app`) exposes `/process`, `/ui`, and OpenAPI docs for API-driven use.

## Deploy on Render (Docker)

This repo includes a root `Dockerfile` that runs Streamlit and installs OCR system deps (Tesseract + Poppler).

- **Render service**: New → Web Service → connect your GitHub repo
- **Runtime**: Docker
- **Environment variables**:
  - `GROQ_API_KEY` (required)
  - Optional: `GROQ_MODEL`, `GROQ_TEMPERATURE`

Render provides a `PORT` environment variable automatically; the container starts Streamlit on `${PORT}`.

## Prerequisites

- Python 3.10+
- A [Groq](https://console.groq.com/) API key

## Setup (local)

1. Enter the project folder:

   ```bash
   cd First_CrewAI
   ```

2. Virtual environment (recommended):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   For a **minimal** set similar to the Space: `pip install -r requirements-space.txt`

4. Environment:

   - Copy `.env.example` to `.env`.
   - Set `GROQ_API_KEY`. Optional: `GROQ_MODEL`, `GROQ_TEMPERATURE` (default `0.3` for summarizer).

   ```env
   GROQ_API_KEY=your_groq_api_key_here
   GROQ_MODEL=llama-3.1-8b-instant
   GROQ_TEMPERATURE=0.3
   ```

## Run Streamlit UI (recommended)

```bash
streamlit run streamlit_app.py
```

Open [http://localhost:8501](http://localhost:8501).

**Features:** metrics after each run, **final report PDF**, per-agent PDFs under **Agent-by-agent**, copy-friendly text preview.

## Run the API (optional)

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Built-in HTML UI: `http://127.0.0.1:8000/ui` (same host/port as uvicorn)

<img width="1626" height="858" alt="1 py" src="https://github.com/user-attachments/assets/635978fc-ba18-44b5-964d-9cbc8ba18781" />


<img width="1532" height="856" alt="4 py" src="https://github.com/user-attachments/assets/2af40753-4411-45b4-b366-aea2d00ef3a3" />


## API reference (FastAPI)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service status |
| `GET` | `/models` | Groq models for your key |
| `POST` | `/process` | Full pipeline |
| `GET` | `/ui` | Simple web UI |
| `POST` | `/process/upload` | PDF upload + pipeline |

### `POST /process` body (example)

```json
{
  "source": "https://www.youtube.com/watch?v=...",
  "platform": "twitter",
  "tone": "professional",
  "output_language": "english",
  "glossary": "optional, comma-separated names"
}
```

- **platform:** `twitter` | `linkedin` | `instagram`
- **tone:** `professional` | `casual` | `funny` | `empathetic`
- **output_language:** `match_source` | `english` | `hindi` | `french` (Streamlit UI offers English / Hindi)

## Scanned PDFs (OCR)

If a PDF has no extractable text, the app can use **Tesseract** + **Poppler** (Docker Space installs both). On Windows, install Poppler and Tesseract and optionally set `TESSERACT_CMD` / `POPPLER_PATH` in `.env`.

## Architecture (agents)

1. **Content extractor** — YouTube transcripts, article HTML, or PDF text (`pypdf`; OCR if needed). Cached ~1 hour per source.
2. **Summarizer** — Groq bullet-style summary (temperature from `GROQ_TEMPERATURE`).
3. **Platform adapter** — Draft with platform limits (e.g. Twitter `---TWEET---` separators).
4. **Tone adjuster** — Groq rewrite in the chosen tone.
5. **Translator** — Runs when output language is **Hindi**.

Groq calls use shared **`GroqClient`** with exponential backoff (up to **3** attempts); auth errors are not retried. Long inputs use **chunked** summarization where needed.

## License

Use and modify as needed for your own projects.

