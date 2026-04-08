"""Streamlit entrypoint for Hugging Face Spaces and local runs."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
NESTED_ROOT = ROOT / "First_CrewAI"
if NESTED_ROOT.exists() and str(NESTED_ROOT) not in sys.path:
    sys.path.insert(0, str(NESTED_ROOT))

import streamlit as st
from pypdf import PdfReader

try:
    from app.config import get_settings
    from app.ocr import ocr_pdf_bytes_to_text
    from app.pipeline_full import run_from_source, run_text_pipeline
    from app.ui_trace import pipeline_step_panels
except ModuleNotFoundError as _import_err:
    if getattr(_import_err, "name", None) != "app":
        raise
    from First_CrewAI.app.config import get_settings
    from First_CrewAI.app.ocr import ocr_pdf_bytes_to_text
    from First_CrewAI.app.pipeline_full import run_from_source, run_text_pipeline
    from First_CrewAI.app.ui_trace import pipeline_step_panels

st.set_page_config(
    page_title="Multi-Agent Content Studio",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    html, body, [class*="css"] {
        font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .block-container { padding-top: 1rem; max-width: 1200px; }
    div[data-testid="stDecoration"] { display: none; }
    .studio-hero {
        background: linear-gradient(135deg, rgba(255,127,80,0.35) 0%, rgba(17,27,49,0.92) 45%, #0b1120 100%);
        border: 1px solid #253559;
        border-radius: 16px;
        padding: 1.35rem 1.5rem;
        margin-bottom: 1.25rem;
    }
    .studio-hero h1 { margin: 0 0 0.35rem 0; font-size: 1.65rem; color: #eaf0ff; font-weight: 700; }
    .studio-hero p { margin: 0; color: #a8b7d8; font-size: 0.95rem; line-height: 1.5; }
    .studio-dot {
        display: inline-block; width: 10px; height: 10px; border-radius: 50%;
        background: #6ef2a7; margin-right: 10px;
        box-shadow: 0 0 12px rgba(110,242,167,0.5);
        vertical-align: middle;
    }
    .step-chip {
        display: inline-block; padding: 0.2rem 0.65rem; border-radius: 999px;
        background: rgba(255,127,80,0.15); border: 1px solid rgba(255,127,80,0.35);
        color: #ffcba4; font-size: 0.78rem; margin: 0.15rem 0.25rem 0.15rem 0;
    }
    div[data-testid="stSidebarContent"] {
        background: linear-gradient(180deg, #0f172a 0%, #0b1120 100%);
    }
</style>
""",
    unsafe_allow_html=True,
)

if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None
if "run_id" not in st.session_state:
    st.session_state.run_id = 0
if "last_run_options" not in st.session_state:
    st.session_state.last_run_options = {}
if "last_download_slug" not in st.session_state:
    st.session_state.last_download_slug = "run"


def _dynamic_slug(*, platform: str, tone: str, language: str, run_id: int) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{platform}_{tone}_{language}_{ts}_r{run_id}"


def _run_url(source: str, platform: str, tone: str, language: str) -> bool:
    source = (source or "").strip()
    if not source:
        st.error("Paste a YouTube or blog/article URL first.")
        return False
    try:
        with st.status("Running your multi-agent pipeline…", expanded=True) as status:
            status.write("Agent 1 · Pulling text from your link…")
            out = asyncio.run(run_from_source(source, platform, tone, language))
            status.write("Agents 2–4 · Summarize → platform draft → tone…")
            if (language or "").lower().strip() == "hindi":
                status.write("Agent 5 · Translating to Hindi…")
            status.update(label="Pipeline finished", state="complete", expanded=False)
        st.session_state.pipeline_result = out
        st.session_state.run_id += 1
        st.session_state.last_run_options = {
            "platform": platform,
            "tone": tone,
            "language": language,
        }
        st.session_state.last_download_slug = _dynamic_slug(
            platform=platform, tone=tone, language=language, run_id=st.session_state.run_id
        )
        st.toast("Content ready. Scroll down to Results.")
        return True
    except Exception as e:
        st.error(str(e))
        return False


def _run_pdf_bytes(data: bytes, platform: str, tone: str, language: str) -> bool:
    try:
        reader = PdfReader(BytesIO(data))
        raw_text = "\n".join((pg.extract_text() or "") for pg in reader.pages).strip()
        if not raw_text:
            try:
                raw_text = ocr_pdf_bytes_to_text(data, max_pages=30)
            except ImportError:
                st.error(
                    "This PDF looks like a scan. Install **pdf2image**, **pytesseract**, and "
                    "system **Tesseract + Poppler**, or use a text-based PDF."
                )
                return False
            except Exception as e:
                st.error(
                    "OCR failed for this PDF. On Hugging Face, confirm Docker installed "
                    "`tesseract-ocr` and `poppler-utils`; locally, install Tesseract/Poppler "
                    f"and retry.\n\nDetails: {e}"
                )
                return False
        if not raw_text:
            st.error("No text could be extracted from this PDF.")
            return False
        with st.status("Running your multi-agent pipeline…", expanded=True) as status:
            status.write("Agent 1 · Using extracted PDF text…")
            out = asyncio.run(run_text_pipeline(raw_text, platform, tone, language))
            status.write("Agents 2–4 · Summarize → platform draft → tone…")
            if (language or "").lower().strip() == "hindi":
                status.write("Agent 5 · Translating to Hindi…")
            status.update(label="Pipeline finished", state="complete", expanded=False)
        st.session_state.pipeline_result = out
        st.session_state.run_id += 1
        st.session_state.last_run_options = {
            "platform": platform,
            "tone": tone,
            "language": language,
        }
        st.session_state.last_download_slug = _dynamic_slug(
            platform=platform, tone=tone, language=language, run_id=st.session_state.run_id
        )
        st.toast("Content ready. Scroll down to Results.")
        return True
    except Exception as e:
        st.error(str(e))
        return False


# —— Sidebar ——
with st.sidebar:
    st.markdown("### Controls")
    platform = st.selectbox(
        "Target platform",
        ["twitter", "linkedin", "instagram"],
        index=0,
        help="Each platform gets different length limits and hashtag rules.",
    )
    tone = st.selectbox(
        "Voice / tone",
        ["professional", "casual", "funny", "empathetic"],
        index=0,
    )
    language = st.selectbox(
        "Output language",
        ["english", "hindi"],
        index=0,
        help="Hindi runs an extra translation agent after tone pass.",
    )
    st.divider()
    _s = get_settings()
    if not (_s.get("groq_api_key") or "").strip():
        st.error("Set **GROQ_API_KEY** in `.env` or HF Secrets.")
    with st.expander("How the agents run", expanded=False):
        st.markdown(
            """
1. **Extractor** — YouTube transcript, article HTML, or PDF text (OCR if needed).  
2. **Summarizer** — Bullet-style summary in English.  
3. **Platform adapter** — Draft sized for Twitter / LinkedIn / Instagram.  
4. **Tone adjuster** — Rewrites in your chosen tone.  
5. **Translator** — Only if you pick **Hindi**.
            """
        )


# —— Hero ——
st.markdown(
    """
<div class="studio-hero">
  <h1><span class="studio-dot"></span>Multi-Agent Content Studio</h1>
  <p>
    Turn a <strong>URL</strong> or <strong>PDF</strong> into platform-ready posts.
    Watch each agent’s output below after you generate.
  </p>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<span class="step-chip">Extract</span>'
    '<span class="step-chip">Summarize</span>'
    '<span class="step-chip">Adapt</span>'
    '<span class="step-chip">Tone</span>'
    '<span class="step-chip">Translate</span>',
    unsafe_allow_html=True,
)

tab_url, tab_pdf = st.tabs(["Link to content", "Upload PDF"])

with tab_url:
    st.markdown("Paste a **YouTube** watch URL or a **blog / article** link.")
    source = st.text_input(
        "URL",
        label_visibility="collapsed",
        placeholder="https://www.youtube.com/watch?v=…  or  https://example.com/article",
    )
    col_go, col_hint = st.columns([1, 2])
    with col_go:
        go_url = st.button("Run all agents", type="primary", use_container_width=True, key="go_url")
    with col_hint:
        st.caption("Uses your sidebar settings: **{0}** · **{1}** · **{2}**".format(platform, tone, language))
    if go_url:
        _run_url(source, platform, tone, language)

with tab_pdf:
    uploaded = st.file_uploader("Choose PDF", type=["pdf"], accept_multiple_files=False)
    if uploaded is not None:
        st.caption(f"Selected: **{uploaded.name}** ({len(uploaded.getvalue()) // 1024} KB)")
    col_go2, _ = st.columns([1, 2])
    with col_go2:
        go_pdf = st.button("Run all agents", type="primary", use_container_width=True, key="go_pdf")
    if go_pdf:
        if uploaded is None:
            st.warning("Choose a PDF file first.")
        else:
            _run_pdf_bytes(uploaded.getvalue(), platform, tone, language)

st.divider()

# —— Results ——
st.subheader("Results")
out = st.session_state.pipeline_result

if out is None:
    st.info("Run the pipeline from a **link** or **PDF** to see the final post and each agent’s output here.")
else:
    final = (out.get("final_text") or "").strip()
    raw_len = len((out.get("raw_text") or ""))
    sum_len = len((out.get("summary") or ""))
    opts = st.session_state.get("last_run_options") or {}
    rp = opts.get("platform", platform)
    rt = opts.get("tone", tone)
    rl = opts.get("language", language)
    src_hint = str(out.get("source_kind") or "PDF upload")
    slug = st.session_state.get("last_download_slug") or _dynamic_slug(
        platform=rp, tone=rt, language=rl, run_id=st.session_state.run_id
    )
    final_report_text = (
        "Final report\n"
        f"Platform: {rp}\n"
        f"Tone: {rt}\n"
        f"Language: {rl}\n"
        f"Source: {src_hint}\n"
        "Final post from the tone adjuster and translator (if Hindi).\n"
        "---\n"
        f"{final}\n"
    )

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Extracted chars", f"{raw_len:,}")
    with m2:
        st.metric("Summary chars", f"{sum_len:,}")
    with m3:
        st.metric("Final chars", f"{len(final):,}")
    with m4:
        sk = out.get("source_kind") or "pdf"
        st.metric("Source", str(sk)[:18] + ("…" if len(str(sk)) > 18 else ""))

    st.markdown(
        "**Final report (.txt)** — exact output text from the last agents (tone / translate). "
        "Per-agent `.txt` downloads are under **Agent-by-agent**."
    )

    dl1, dl2 = st.columns([1, 1])
    with dl1:
        st.download_button(
            label="Download final report · TXT",
            data=final_report_text,
            file_name=f"final_report_{slug}.txt",
            mime="text/plain",
            use_container_width=True,
            key="dl_report_txt_top",
        )
    with dl2:
        if st.button("Clear results", use_container_width=True, key="clear_top"):
            st.session_state.pipeline_result = None
            st.session_state.last_run_options = {}
            st.rerun()

    out_tab, agents_tab = st.tabs(["Final post", "Agent-by-agent"])
    with out_tab:
        st.caption("Copy from the box or download **final_report.txt** above.")
        st.text_area(
            "Ready to copy",
            value=final,
            height=280,
            disabled=True,
            label_visibility="collapsed",
            key=f"final_out_{st.session_state.run_id}",
        )
        st.download_button(
            "Download final report (.txt)",
            data=final_report_text,
            file_name=f"final_report_{slug}.txt",
            mime="text/plain",
            use_container_width=True,
            key="dl_report_txt_tab",
        )
    with agents_tab:
        st.caption("Each row: preview + **Download .txt** for that agent only.")
        rid = st.session_state.run_id
        for i, (short, full_title, body) in enumerate(pipeline_step_panels(out)):
            h = min(400, max(140, 80 + body.count("\n") * 16))
            safe_name = "".join(c if c.isalnum() else "_" for c in short)[:40] or f"step_{i + 1}"
            step_text = f"{full_title}\nStep: {short}\n---\n{body}\n"
            with st.expander(f"{full_title} · {short}", expanded=False):
                st.text_area(
                    "output",
                    value=body,
                    height=h,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"agent_{rid}_{i}",
                )
                st.download_button(
                    f"Download this agent · TXT ({short})",
                    data=step_text,
                    file_name=f"agent_{i + 1}_{safe_name}_{slug}.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key=f"dl_agent_txt_{rid}_{i}",
                )
