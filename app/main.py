"""FastAPI application: multi-agent content repurposing (Groq + optional CrewAI)."""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pypdf import PdfReader

from app.agents.platform_adapter import adapt_for_platform
from app.agents.summarizer import summarize_text
from app.agents.tone_adjuster import adjust_tone
from app.config import get_env_diagnostics, get_settings
from app.crew_runner import run_crewai_pipeline
from app.groq_client import groq_client
from app.library_loader import load_brand_profiles, load_templates
from app.ocr import ocr_pdf_bytes_to_text, ocr_runtime_status
from app.orchestrator import process_raw_text
from app.pipeline_full import run_from_source
from app.platform_validation import validate_both_stages
from app.schemas import (
    HealthResponse,
    ModelsResponse,
    ProcessRequest,
    ProcessResponse,
)
from app.source_extraction import extract_raw_from_source

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Multi-Agent Content Repurposing",
    description="Extract → Summarize → Adapt → Tone → Translate",
    version="2.0.0",
)

_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Multi-Agent Content Repurposing</title>
  <style>
    :root {
      --bg: #090f1f;
      --surface: #111a30;
      --surface-2: #0d1529;
      --text: #e9efff;
      --muted: #9fb2d8;
      --line: #223150;
      --brand: #4e7cff;
      --brand-2: #6a8cff;
      --ok: #2cc981;
      --warn: #f6b94b;
      --shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
    }
    * { box-sizing: border-box; }
    html, body {
      height: 100%;
      margin: 0;
      overflow: hidden;
    }
    body {
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #223866 0%, transparent 60%), var(--bg);
      color: var(--text);
    }
    .wrap {
      max-width: 1220px;
      margin: 0 auto;
      padding: 12px 16px;
      height: 100%;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .hero {
      flex-shrink: 0;
      background: linear-gradient(135deg, rgba(78,124,255,.25), rgba(106,140,255,.06));
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 12px 14px 10px;
      box-shadow: var(--shadow);
      animation: fadeIn .35s ease;
    }
    h1 { margin: 0 0 4px; font-size: 20px; letter-spacing:.2px; }
    p { margin: 0; color: var(--muted); }

    .grid {
      flex: 1;
      min-height: 0;
      display: grid;
      grid-template-columns: minmax(280px, 380px) 1fr;
      gap: 12px;
      margin-top: 10px;
      align-items: stretch;
    }
    .card {
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
      overscroll-behavior: contain;
      -webkit-overflow-scrolling: touch;
      background: linear-gradient(180deg, var(--surface), var(--surface-2));
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      box-shadow: var(--shadow);
      animation: fadeIn .4s ease;
    }

    .section-title {
      margin: 0 0 10px;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: .8px;
      color: var(--muted);
    }

    .tabs { display: flex; gap: 8px; margin-bottom: 10px; }
    .tab {
      flex: 1;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #0f1730;
      color: var(--text);
      cursor: pointer;
      transition: .18s ease;
    }
    .tab:hover { border-color: #355089; }
    .tab.active {
      border-color: var(--brand);
      box-shadow: inset 0 0 0 1px rgba(78,124,255,.45);
      background: #122044;
    }

    label { display: block; font-size: 12px; color: var(--muted); margin: 9px 0 6px; }
    input[type="text"], select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #0e1732;
      color: var(--text);
      padding: 10px 11px;
      outline: none;
      transition: border-color .2s ease;
    }
    input:focus, select:focus, textarea:focus { border-color: var(--brand); }
    textarea { min-height: 74px; resize: vertical; }
    input[type="file"] { width: 100%; color: var(--muted); }

    .row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
    .actions { display: flex; gap: 10px; margin-top: 12px; }
    .btn {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 14px;
      color: white;
      font-weight: 600;
      cursor: pointer;
      transition: transform .12s ease, opacity .2s ease;
    }
    .btn:active { transform: translateY(1px); }
    .btn:disabled { opacity: .65; cursor: not-allowed; }
    .btn-primary {
      background: linear-gradient(180deg, var(--brand-2), #3e67e0);
      border-color: #3a5fcf;
      flex: 1;
    }
    .btn-secondary { background: #0f1730; }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      color: var(--muted);
      background: #0e1730;
      margin-right: 8px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #5d6f93;
    }
    .dot.active {
      background: var(--warn);
      box-shadow: 0 0 0 4px rgba(246,185,75,.16);
      animation: pulse 1.2s infinite;
    }
    .dot.done { background: var(--ok); box-shadow: 0 0 0 4px rgba(44,201,129,.12); }

    .status { margin-top: 10px; font-size: 13px; color: var(--muted); min-height: 20px; }
    .warn {
      margin-top: 10px;
      font-size: 12px;
      color: #ffd89e;
      background: #3a2610;
      border: 1px solid #7e5120;
      border-radius: 10px;
      padding: 10px;
      display: none;
    }
    .small { font-size: 12px; color: var(--muted); margin-top: 10px; }
    .quick-links {
      margin-top: 10px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .quick-link {
      text-decoration: none;
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 12px;
      background: #0f1730;
    }
    .quick-link:hover { border-color: var(--brand); }

    .agents {
      min-height: 0;
      display: flex;
      flex-direction: column;
      gap: 10px;
      overflow: hidden;
      padding-right: 2px;
    }
    .agent-box {
      display: flex;
      flex-direction: column;
      min-height: 0;
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      background: #0b1328;
      transition: border-color .2s ease, transform .16s ease;
    }
    .agent-outputs {
      display: none;
    }
    .agents > .agent-box.final {
      flex: 1;
      max-height: none;
      min-height: 420px;
    }
    .agents > .agent-box:not(.final) {
      flex: 1;
      min-height: 160px;
    }
    .agent-tabs {
      display: flex;
      gap: 8px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      background: #0e1732;
      flex-wrap: wrap;
    }
    .agent-pages-note {
      padding: 8px 12px;
      color: var(--muted);
      font-size: 12px;
      border-bottom: 1px solid var(--line);
      background: #0c1530;
    }
    .agent-tab-btn {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 7px 10px;
      background: #101b38;
      color: var(--text);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }
    .agent-tab-btn.active {
      border-color: var(--brand);
      box-shadow: inset 0 0 0 1px rgba(78,124,255,.45);
      background: #122044;
    }
    .agent-viewer-title {
      padding: 8px 12px;
      color: var(--muted);
      font-size: 12px;
      border-bottom: 1px solid var(--line);
    }
    .agent-box > .agent-head,
    .agent-box > div:not(.agent-head):not(pre) {
      flex-shrink: 0;
    }
    .agent-box:hover { border-color: #395796; }
    .agent-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px;
      background: #101b38;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
      font-weight: 600;
    }
    .agent-state {
      font-size: 11px;
      color: var(--muted);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 8px;
      background: #0f1730;
    }
    .agent-state.active { color: #ffd89e; border-color: #7e5120; }
    .agent-state.done { color: #7ff1b8; border-color: #1f7f53; }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      padding: 12px;
      color: var(--text);
    }
    .agent-box pre {
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
    }
    #agentViewer {
      scrollbar-width: thin;
      scrollbar-color: #4e7cff #0e1732;
      overscroll-behavior: contain;
      touch-action: pan-y;
    }
    #agentViewer::-webkit-scrollbar { width: 10px; }
    #agentViewer::-webkit-scrollbar-track { background: #0e1732; }
    #agentViewer::-webkit-scrollbar-thumb {
      background: #4e7cff;
      border-radius: 999px;
      border: 2px solid #0e1732;
    }
    #finalResult {
      overflow: visible;
      max-height: none;
      min-height: 520px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    @keyframes pulse {
      0% { transform: scale(1); opacity: 1; }
      50% { transform: scale(1.2); opacity: .75; }
      100% { transform: scale(1); opacity: 1; }
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 1024px) {
      html, body {
        height: auto;
        min-height: 100dvh;
        overflow: auto;
      }
      .wrap {
        height: auto;
        min-height: 100dvh;
      }
      .grid {
        flex: none;
        grid-template-columns: 1fr;
      }
      .agents {
        min-height: min(70dvh, 520px);
        overflow: visible;
      }
      .agents > .agent-box.final {
        flex: none;
        max-height: none;
        min-height: 200px;
      }
      .agents > .agent-box:not(.final) {
        flex: none;
        min-height: min(55dvh, 480px);
      }
      .agent-box pre {
        max-height: min(50dvh, 420px);
      }
      .row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>Multi-Agent Content Repurposing Studio</h1>
      <p>See each agent output step-by-step: Extractor -> Summarizer -> Platform Adapter -> Tone Adjuster.</p>
    </div>

    <div class="grid">
      <div class="card">
        <div class="section-title">Input</div>
        <div class="tabs">
          <button class="tab active" id="tabUpload" type="button">Upload PDF</button>
          <button class="tab" id="tabUrl" type="button">YouTube / Blog Link</button>
        </div>

        <div id="paneUpload">
          <label>PDF file</label>
          <input id="pdfFile" type="file" accept=".pdf,application/pdf" />
        </div>

        <div id="paneUrl" style="display:none;">
          <label>Source (YouTube URL or blog URL)</label>
          <input id="sourceUrl" type="text" placeholder="https://www.youtube.com/watch?v=... or https://example.com/blog" />
        </div>

        <div class="row">
          <div>
            <label>Platform</label>
            <select id="platform">
              <option value="twitter">twitter</option>
              <option value="linkedin">linkedin</option>
              <option value="instagram">instagram</option>
            </select>
          </div>
          <div>
            <label>Tone</label>
            <select id="tone">
              <option value="professional">professional</option>
              <option value="casual">casual</option>
              <option value="funny">funny</option>
              <option value="empathetic">empathetic</option>
            </select>
          </div>
          <div>
            <label>Language</label>
            <select id="language">
              <option value="english">english</option>
              <option value="hindi">hindi</option>
            </select>
          </div>
        </div>

        <div class="actions">
          <button id="runBtn" class="btn btn-primary" type="button">Run Pipeline</button>
          <button id="clearBtn" class="btn btn-secondary" type="button">Clear</button>
        </div>

        <div style="margin-top:12px;">
          <span class="pill"><span id="dotA1" class="dot"></span>Agent 1</span>
          <span class="pill"><span id="dotA2" class="dot"></span>Agent 2</span>
          <span class="pill"><span id="dotA3" class="dot"></span>Agent 3</span>
          <span class="pill"><span id="dotA4" class="dot"></span>Agent 4</span>
        </div>
        <div id="status" class="status">Idle.</div>
        <div class="quick-links">
          <a class="quick-link" href="/ui/agent/1" target="_blank" rel="noopener">Agent 1</a>
          <a class="quick-link" href="/ui/agent/2" target="_blank" rel="noopener">Agent 2</a>
          <a class="quick-link" href="/ui/agent/3" target="_blank" rel="noopener">Agent 3</a>
          <a class="quick-link" href="/ui/agent/4" target="_blank" rel="noopener">Agent 4</a>
          <a class="quick-link" href="/ui/final" target="_blank" rel="noopener">Final</a>
        </div>
        <div class="small">Tip: if API key is missing, check <code>/debug/config</code>.</div>
        <div id="ocrWarn" class="warn"></div>
      </div>

      <div class="agents">
        <div class="agent-box final">
          <div class="agent-head">
            <span>Final Result</span>
            <span class="agent-state" id="stateFinal">waiting</span>
          </div>
          <div style="padding:8px 12px; color:var(--muted); font-size:12px;">Final publish-ready output after Agent 4</div>
          <div style="padding:8px 12px; border-bottom:1px solid var(--line); display:flex; gap:8px; flex-wrap:wrap;">
            <button id="exportPdfBtn" class="btn btn-secondary" type="button" style="padding:8px 12px;">Export Final Result PDF</button>
          </div>
          <pre id="finalResult"></pre>
        </div>

        <div class="agent-box agent-outputs">
          <div class="agent-head">
            <span>Agent Outputs</span>
            <span class="agent-state done">click tabs</span>
          </div>
          <div class="agent-pages-note">
            Separate pages:
            <a class="agent-tab-btn" href="/ui/agent/1" target="_blank" rel="noopener">Agent 1</a>
            <a class="agent-tab-btn" href="/ui/agent/2" target="_blank" rel="noopener">Agent 2</a>
            <a class="agent-tab-btn" href="/ui/agent/3" target="_blank" rel="noopener">Agent 3</a>
            <a class="agent-tab-btn" href="/ui/agent/4" target="_blank" rel="noopener">Agent 4</a>
            <a class="agent-tab-btn" href="/ui/final" target="_blank" rel="noopener">Final</a>
          </div>
          <div class="agent-tabs">
            <button id="agentTab1" class="agent-tab-btn active" type="button">Agent 1</button>
            <button id="agentTab2" class="agent-tab-btn" type="button">Agent 2</button>
            <button id="agentTab3" class="agent-tab-btn" type="button">Agent 3</button>
            <button id="agentTab4" class="agent-tab-btn" type="button">Agent 4</button>
          </div>
          <div id="agentViewerTitle" class="agent-viewer-title">Agent 1 — Extractor</div>
          <pre id="agentViewer"></pre>
        </div>
      </div>
    </div>
  </div>

<script>
  const tabUpload = document.getElementById('tabUpload');
  const tabUrl = document.getElementById('tabUrl');
  const paneUpload = document.getElementById('paneUpload');
  const paneUrl = document.getElementById('paneUrl');
  const runBtn = document.getElementById('runBtn');
  const clearBtn = document.getElementById('clearBtn');
  const exportPdfBtn = document.getElementById('exportPdfBtn');
  const statusEl = document.getElementById('status');
  const ocrWarnEl = document.getElementById('ocrWarn');
  const agentViewerEl = document.getElementById('agentViewer');
  const agentViewerTitleEl = document.getElementById('agentViewerTitle');
  const agentTab1 = document.getElementById('agentTab1');
  const agentTab2 = document.getElementById('agentTab2');
  const agentTab3 = document.getElementById('agentTab3');
  const agentTab4 = document.getElementById('agentTab4');

  const dotA1 = document.getElementById('dotA1');
  const dotA2 = document.getElementById('dotA2');
  const dotA3 = document.getElementById('dotA3');
  const dotA4 = document.getElementById('dotA4');

  const stateA1 = document.getElementById('stateA1');
  const stateA2 = document.getElementById('stateA2');
  const stateA3 = document.getElementById('stateA3');
  const stateA4 = document.getElementById('stateA4');
  const stateFinal = document.getElementById('stateFinal');
  const finalResultEl = document.getElementById('finalResult');

  const outputs = {
    raw: '',
    summary: '',
    draft: '',
    final: '',
    validation: ''
  };
  const OUTPUTS_STORAGE_KEY = 'repurpose_outputs_v1';
  let activeAgentTab = 1;

  function persistOutputs() {
    try {
      localStorage.setItem(OUTPUTS_STORAGE_KEY, JSON.stringify(outputs));
    } catch (e) {}
  }

  function loadOutputsFromStorage() {
    try {
      const raw = localStorage.getItem(OUTPUTS_STORAGE_KEY);
      if (!raw) return false;
      const saved = JSON.parse(raw) || {};
      outputs.raw = saved.raw || '';
      outputs.summary = saved.summary || '';
      outputs.draft = saved.draft || '';
      outputs.final = saved.final || '';
      outputs.validation = saved.validation || '';
      finalResultEl.textContent = outputs.final || '';
      return !!(outputs.raw || outputs.summary || outputs.draft || outputs.final);
    } catch (e) {
      return false;
    }
  }

  function renderAgentTabs() {
    const map = {
      1: { title: 'Agent 1 — Extractor', content: outputs.raw || '' },
      2: { title: 'Agent 2 — Summarizer', content: outputs.summary || '' },
      3: { title: 'Agent 3 — Platform Adapter', content: outputs.draft || '' },
      4: { title: 'Agent 4 — Tone + Validation', content: (outputs.final || '') + ((outputs.validation || '') ? `\n\n--- Validation ---\n${outputs.validation}` : '') }
    };
    const current = map[activeAgentTab] || map[1];
    agentViewerTitleEl.textContent = current.title;
    agentViewerEl.textContent = current.content;
    agentTab1.classList.toggle('active', activeAgentTab === 1);
    agentTab2.classList.toggle('active', activeAgentTab === 2);
    agentTab3.classList.toggle('active', activeAgentTab === 3);
    agentTab4.classList.toggle('active', activeAgentTab === 4);
  }

  function renderOutputs() {
    renderAgentTabs();
    persistOutputs();
  }

  let mode = 'upload';
  let stepTimerId = null;
  let stepStartedAt = 0;
  let stepLabel = '';

  function setMode(next) {
    mode = next;
    tabUpload.classList.toggle('active', mode === 'upload');
    tabUrl.classList.toggle('active', mode === 'url');
    paneUpload.style.display = mode === 'upload' ? '' : 'none';
    paneUrl.style.display = mode === 'url' ? '' : 'none';
  }
  tabUpload.addEventListener('click', () => setMode('upload'));
  tabUrl.addEventListener('click', () => setMode('url'));
  agentTab1.addEventListener('click', () => { activeAgentTab = 1; renderAgentTabs(); });
  agentTab2.addEventListener('click', () => { activeAgentTab = 2; renderAgentTabs(); });
  agentTab3.addEventListener('click', () => { activeAgentTab = 3; renderAgentTabs(); });
  agentTab4.addEventListener('click', () => { activeAgentTab = 4; renderAgentTabs(); });

  function resetAgentStates() {
    for (const d of [dotA1, dotA2, dotA3, dotA4]) {
      if (d) d.className = 'dot';
    }
    for (const s of [stateA1, stateA2, stateA3, stateA4, stateFinal]) {
      if (!s) continue;
      s.className = 'agent-state';
      s.textContent = 'waiting';
    }
    finalResultEl.textContent = '';
  }

  function setAgentState(agentNo, state) {
    const dotMap = {1: dotA1, 2: dotA2, 3: dotA3, 4: dotA4};
    const textMap = {1: stateA1, 2: stateA2, 3: stateA3, 4: stateA4};
    const dot = dotMap[agentNo];
    const txt = textMap[agentNo];
    if (!dot || !txt) return;
    dot.className = 'dot';
    txt.className = 'agent-state';
    if (state === 'active') {
      dot.classList.add('active');
      txt.classList.add('active');
      txt.textContent = 'running';
    } else if (state === 'done') {
      dot.classList.add('done');
      txt.classList.add('done');
      txt.textContent = 'done';
    } else if (state === 'error') {
      txt.textContent = 'error';
    } else {
      txt.textContent = 'waiting';
    }
  }

  function clearOutputs() {
    statusEl.textContent = 'Idle.';
    outputs.raw = '';
    outputs.summary = '';
    outputs.draft = '';
    outputs.final = '';
    outputs.validation = '';
    renderOutputs();
    resetAgentStates();
    exportPdfBtn.disabled = true;
    if (stepTimerId) {
      clearInterval(stepTimerId);
      stepTimerId = null;
    }
  }
  clearBtn.addEventListener('click', clearOutputs);

  function inferAgentProgress(data) {
    if ((data.raw_text || '').trim()) setAgentState(1, 'done');
    if ((data.summary || '').trim()) setAgentState(2, 'done');
    if ((data.platform_draft || '').trim()) setAgentState(3, 'done');
    if ((data.final_text || '').trim()) setAgentState(4, 'done');
  }

  function startStepStatus(label) {
    stepLabel = label;
    stepStartedAt = Date.now();
    if (stepTimerId) clearInterval(stepTimerId);
    statusEl.textContent = label + '... 0s';
    stepTimerId = setInterval(() => {
      const secs = Math.floor((Date.now() - stepStartedAt) / 1000);
      statusEl.textContent = `${stepLabel}... ${secs}s`;
    }, 1000);
  }

  function finishStepStatus(doneMessage) {
    if (stepTimerId) {
      clearInterval(stepTimerId);
      stepTimerId = null;
    }
    statusEl.textContent = doneMessage;
  }

  async function run() {
    runBtn.disabled = true;
    exportPdfBtn.disabled = true;
    clearOutputs();
    setAgentState(1, 'active');
    startStepStatus('Running pipeline');

    const platform = document.getElementById('platform').value;
    const tone = document.getElementById('tone').value;
    const language = document.getElementById('language').value;
    try {
      let resp, data;
      if (mode === 'upload') {
        const file = document.getElementById('pdfFile').files[0];
        if (!file) throw new Error('Please choose a PDF file.');
        const fd = new FormData();
        fd.append('file', file);
        fd.append('platform', platform);
        fd.append('tone', tone);
        fd.append('language', language);
        resp = await fetch('/process/upload', { method: 'POST', body: fd });
        data = await resp.json();
      } else {
        const source = document.getElementById('sourceUrl').value.trim();
        if (!source) throw new Error('Please enter a YouTube or blog URL.');
        resp = await fetch('/process', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source, platform, tone, language })
        });
        data = await resp.json();
      }

      if (!resp.ok || data.success === false) {
        throw new Error(data.detail || data.error || JSON.stringify(data));
      }
      outputs.raw = data.raw_text || '';
      outputs.summary = data.summary || '';
      outputs.draft = data.platform_draft || '';
      outputs.final = data.final_text || '';
      outputs.validation = JSON.stringify(data.character_validation || {}, null, 2);
      finalResultEl.textContent = outputs.final;
      renderOutputs();
      inferAgentProgress(data);
      stateFinal.className = 'agent-state done';
      stateFinal.textContent = 'ready';
      finishStepStatus(`Pipeline completed (${data.source_kind || mode}).`);
      exportPdfBtn.disabled = false;
    } catch (e) {
      finishStepStatus('Error: ' + e.message);
    } finally {
      runBtn.disabled = false;
    }
  }
  runBtn.addEventListener('click', run);

  function exportFinalAsPdf() {
    const finalText = (outputs.final || '').trim();
    if (!finalText) {
      finishStepStatus('No final text to export.');
      return;
    }
    const platform = document.getElementById('platform').value;
    const tone = document.getElementById('tone').value;
    const now = new Date();
    const title = `Final Social Output - ${platform} (${tone})`;
    const escapedText = finalText
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    const printableHtml = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${title}</title>
  <style>
    @page { size: A4; margin: 18mm; }
    body { font-family: "Segoe UI", Arial, sans-serif; color: #111; line-height: 1.5; white-space: pre-wrap; }
    h1 { font-size: 18px; margin: 0 0 8px; }
    .meta { color: #444; margin-bottom: 14px; font-size: 12px; }
    .box { border: 1px solid #ddd; border-radius: 8px; padding: 12px; }
  </style>
</head>
<body>
  <h1>${title}</h1>
  <div class="meta">Generated: ${now.toLocaleString()}</div>
  <div class="box">${escapedText}</div>
</body>
</html>`;
    const w = window.open('', '_blank');
    if (!w) {
      finishStepStatus('Popup blocked. Allow popups to export PDF.');
      return;
    }
    w.document.open();
    w.document.write(printableHtml);
    w.document.close();
    w.focus();
    setTimeout(() => {
      w.print();
    }, 200);
  }

  exportPdfBtn.addEventListener('click', exportFinalAsPdf);

  async function checkOcr() {
    try {
      const resp = await fetch('/debug/ocr');
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data.ready) {
        const notes = (data.notes || []).map(n => '- ' + n).join('\\n');
        ocrWarnEl.style.display = 'block';
        ocrWarnEl.textContent = 'OCR fallback is not fully ready for scanned PDFs.\\n' + notes;
      }
    } catch (e) {}
  }

  checkOcr();
  const restored = loadOutputsFromStorage();
  if (restored) {
    statusEl.textContent = 'Restored previous output.';
    if (outputs.raw.trim()) setAgentState(1, 'done');
    if (outputs.summary.trim()) setAgentState(2, 'done');
    if (outputs.draft.trim()) setAgentState(3, 'done');
    if (outputs.final.trim()) {
      setAgentState(4, 'done');
      stateFinal.className = 'agent-state done';
      stateFinal.textContent = 'ready';
      exportPdfBtn.disabled = false;
    }
    renderOutputs();
  } else {
    clearOutputs();
    renderOutputs();
  }
</script>
</body>
</html>
"""


@app.get("/")
async def root() -> dict:
    """
    Friendly root route so the base URL doesn't 404.
    """
    return {
        "message": "Multi-Agent Content Repurposing API",
        "ui": "/ui",
        "docs": "/docs",
        "health": "/health",
        "process": "/process",
        "models": "/models",
        "templates": "/templates",
        "brand_profiles": "/brand-profiles",
    }


@app.get("/ui", response_class=HTMLResponse)
async def ui() -> HTMLResponse:
    """Simple built-in UI to try the agents without using Swagger."""
    return HTMLResponse(_UI_HTML)


def _single_output_page_html(title: str, output_key: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: #0b1120;
      color: #e9efff;
    }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 20px; }}
    .card {{
      border: 1px solid #223150;
      border-radius: 14px;
      background: #101a30;
      overflow: hidden;
    }}
    .head {{
      padding: 12px 14px;
      border-bottom: 1px solid #223150;
      font-weight: 700;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .meta {{ color: #9fb2d8; font-size: 12px; }}
    pre {{
      margin: 0;
      padding: 14px;
      min-height: 70vh;
      white-space: pre-wrap;
      word-break: break-word;
      color: #e9efff;
      overflow: visible;
    }}
    .links {{
      margin-bottom: 10px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    a {{
      text-decoration: none;
      color: #e9efff;
      border: 1px solid #223150;
      background: #101a30;
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="links">
      <a href="/ui">Main UI</a>
      <a href="/ui/agent/1">Agent 1</a>
      <a href="/ui/agent/2">Agent 2</a>
      <a href="/ui/agent/3">Agent 3</a>
      <a href="/ui/agent/4">Agent 4</a>
      <a href="/ui/final">Final</a>
    </div>
    <div class="card">
      <div class="head">
        <span>{title}</span>
        <span class="meta" id="meta">waiting for output...</span>
      </div>
      <pre id="out"></pre>
    </div>
  </div>
  <script>
    const key = 'repurpose_outputs_v1';
    const outputKey = '{output_key}';
    const outEl = document.getElementById('out');
    const metaEl = document.getElementById('meta');
    function render() {{
      try {{
        const raw = localStorage.getItem(key);
        if (!raw) {{
          outEl.textContent = 'No output yet. Run pipeline in Main UI first.';
          metaEl.textContent = 'no data';
          return;
        }}
        const data = JSON.parse(raw) || {{}};
        let text = '';
        if (outputKey === 'final_with_validation') {{
          text = (data.final || '') + ((data.validation || '') ? '\\n\\n--- Validation ---\\n' + data.validation : '');
        }} else {{
          text = data[outputKey] || '';
        }}
        outEl.textContent = text || 'No content for this stage yet.';
        metaEl.textContent = 'synced';
      }} catch (e) {{
        outEl.textContent = 'Could not read output from local storage.';
        metaEl.textContent = 'error';
      }}
    }}
    render();
    setInterval(render, 1500);
  </script>
</body>
</html>"""


@app.get("/ui/agent/{agent_no}", response_class=HTMLResponse)
async def ui_agent(agent_no: int) -> HTMLResponse:
    mapping = {
        1: ("Agent 1 Output — Extractor", "raw"),
        2: ("Agent 2 Output — Summarizer", "summary"),
        3: ("Agent 3 Output — Platform Adapter", "draft"),
        4: ("Agent 4 Output — Tone + Validation", "final_with_validation"),
    }
    title, key = mapping.get(agent_no, ("Agent Output", "raw"))
    return HTMLResponse(_single_output_page_html(title, key))


@app.get("/ui/final", response_class=HTMLResponse)
async def ui_final_page() -> HTMLResponse:
    return HTMLResponse(_single_output_page_html("Final Result", "final"))


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness / readiness style health check."""
    return HealthResponse(status="ok")


@app.get("/debug/config")
async def debug_config() -> dict:
    """
    Debug endpoint (safe): confirms whether the server sees GROQ_API_KEY.
    Does NOT return the full key—only a masked prefix/length for troubleshooting.
    """
    s = get_settings()
    key = (s.get("groq_api_key") or "").strip()
    return {
        **get_env_diagnostics(),
        "groq_api_key_present": bool(key),
        "groq_api_key_prefix": (key[:6] + "…") if len(key) >= 6 else "",
        "groq_api_key_length": len(key),
        "groq_model": s.get("groq_model"),
        "groq_temperature_default": s.get("groq_temperature_default"),
    }


@app.get("/debug/ocr")
async def debug_ocr() -> dict:
    """OCR readiness diagnostics for the UI."""
    return ocr_runtime_status()


@app.get("/models", response_model=ModelsResponse)
async def models() -> ModelsResponse:
    """
    List models available to the configured Groq API key and verify
    that GROQ_MODEL (default llama-3.1-8b-instant) appears in the list.
    """
    settings = get_settings()
    target = settings["groq_model"]
    try:
        raw = await groq_client.list_models()
    except Exception as e:
        logger.exception("Failed to list Groq models")
        raise HTTPException(status_code=502, detail=f"Could not list Groq models: {e}") from e

    models_list = [{"id": m["id"]} for m in raw if m.get("id")]
    ids = {m["id"] for m in models_list}
    available = target in ids

    return ModelsResponse(
        models=models_list,
        target_model=target,
        target_model_available=available,
    )


@app.post("/process", response_model=ProcessResponse)
async def process(req: ProcessRequest) -> ProcessResponse:
    """
    Full pipeline for any supported `source` (URL, PDF/media path under project/uploads).
    Set `orchestrator` to `crewai` to run the optional CrewAI sequential crew (slower).
    """
    if req.orchestrator == "crewai":
        try:
            result = await asyncio.to_thread(
                run_crewai_pipeline,
                req.source,
                req.platform,
                req.tone,
                req.language,
                req.glossary,
                req.brand_profile,
                req.template_id,
                req.template_variables or {},
            )
            return ProcessResponse(
                success=True,
                error=None,
                final_text=result.get("final_text", ""),
                final_english=result.get("final_english", ""),
                raw_text=result.get("raw_text", ""),
                summary=result.get("summary", ""),
                platform_draft=result.get("platform_draft", ""),
                character_validation=result.get("character_validation") or {},
                source_kind=result.get("source_kind", "crewai"),
                orchestrator="crewai",
                crew_notes=(result.get("crew_debug") or "")[:8000],
            )
        except Exception as e:
            logger.exception("CrewAI pipeline failed")
            raise HTTPException(status_code=500, detail=str(e)) from e

    try:
        out = await run_from_source(
            req.source,
            req.platform,
            req.tone,
            req.language,
            glossary=req.glossary,
            brand_profile=req.brand_profile,
            template_id=req.template_id,
            template_variables=req.template_variables or {},
        )
        return ProcessResponse(
            success=True,
            error=None,
            final_text=out["final_text"],
            final_english=out["final_english"],
            raw_text=out["raw_text"],
            summary=out["summary"],
            platform_draft=out["platform_draft"],
            character_validation=out["character_validation"],
            source_kind=out.get("source_kind", ""),
            orchestrator="direct",
        )
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.post("/process/upload", response_model=ProcessResponse)
async def process_upload(
    file: UploadFile = File(...),
    platform: str = Form(...),
    tone: str = Form(...),
    output_language: str = Form("match_source"),
    language: str = Form("english"),
    glossary: str = Form(""),
) -> ProcessResponse:
    """
    Upload a PDF file and run the pipeline.

    This uses pypdf directly on the uploaded bytes (no disk write).
    """
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only .pdf uploads are supported.")

    try:
        content = await file.read()
        reader = PdfReader(BytesIO(content))
        parts = [(p.extract_text() or "") for p in reader.pages]
        raw_text = "\n".join(parts).strip()
        if not raw_text:
            # Optional OCR fallback for scanned/image PDFs.
            # Enabled by default if optional deps exist; otherwise return a helpful error.
            try:
                raw_text = ocr_pdf_bytes_to_text(content, max_pages=10)
            except ImportError:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No text could be extracted from the PDF (it may be scanned images). "
                        "OCR fallback is not installed. Install optional deps: "
                        "`pip install pdf2image pytesseract` and (Windows) install Poppler + Tesseract."
                    ),
                )
            except Exception as e:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No text could be extracted from the PDF and OCR fallback failed. "
                        f"Reason: {e}"
                    ),
                ) from e
            if not raw_text:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No text could be extracted from the PDF (pypdf empty and OCR produced no text). "
                        "If it's a scanned document, try a clearer scan or fewer pages."
                    ),
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {e}") from e

    lang = language.strip().lower() if language else "english"
    if lang not in ("english", "hindi"):
        lang = "hindi" if output_language.strip().lower() == "hindi" else "english"
    ol = "hindi" if lang == "hindi" else "english"
    return await process_raw_text(
        raw_text,
        platform,
        tone,
        glossary=glossary,
        output_language=ol,
        source_kind="pdf_upload",
    )


@app.get("/templates")
async def get_templates() -> dict:
    return load_templates()


@app.get("/brand-profiles")
async def get_brand_profiles() -> dict:
    return load_brand_profiles()


@app.post("/agents/extract-source")
async def agent_extract_source(payload: dict) -> dict:
    source = (payload.get("source") or "").strip()
    if not source:
        raise HTTPException(status_code=422, detail="source is required")
    try:
        raw_text, kind = await extract_raw_from_source(source)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Extraction failed: {e}") from e
    return {"raw_text": raw_text, "source_kind": kind}


@app.post("/agents/extract-upload")
async def agent_extract_upload(file: UploadFile = File(...)) -> dict:
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only .pdf uploads are supported.")
    try:
        content = await file.read()
        reader = PdfReader(BytesIO(content))
        parts = [(p.extract_text() or "") for p in reader.pages]
        raw_text = "\n".join(parts).strip()
        if not raw_text:
            raw_text = ocr_pdf_bytes_to_text(content, max_pages=10)
        if not raw_text:
            raise HTTPException(status_code=422, detail="No text extracted from PDF.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Extraction failed: {e}") from e
    return {"raw_text": raw_text}


@app.post("/agents/summarize")
async def agent_summarize(payload: dict) -> dict:
    raw_text = (payload.get("raw_text") or "").strip()
    output_language = (payload.get("output_language") or "match_source").strip().lower()
    glossary = (payload.get("glossary") or "").strip()
    if not raw_text:
        raise HTTPException(status_code=422, detail="raw_text is required")
    try:
        summary = await summarize_text(
            raw_text,
            glossary=glossary,
            output_language=output_language,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Summarization failed: {e}") from e
    return {"summary": summary}


@app.post("/agents/adapt")
async def agent_adapt(payload: dict) -> dict:
    summary = (payload.get("summary") or "").strip()
    platform = (payload.get("platform") or "").strip().lower()
    output_language = (payload.get("output_language") or "match_source").strip().lower()
    glossary = (payload.get("glossary") or "").strip()
    if not summary:
        raise HTTPException(status_code=422, detail="summary is required")
    try:
        platform_draft = await adapt_for_platform(
            summary,
            platform,
            glossary=glossary,
            output_language=output_language,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Platform adaptation failed: {e}") from e
    return {"platform_draft": platform_draft}


@app.post("/agents/tone")
async def agent_tone(payload: dict) -> dict:
    platform_draft = (payload.get("platform_draft") or "").strip()
    platform = (payload.get("platform") or "").strip().lower()
    tone = (payload.get("tone") or "").strip().lower()
    output_language = (payload.get("output_language") or "match_source").strip().lower()
    glossary = (payload.get("glossary") or "").strip()
    if not platform_draft:
        raise HTTPException(status_code=422, detail="platform_draft is required")
    try:
        final_text = await adjust_tone(
            platform_draft,
            platform,
            tone,
            glossary=glossary,
            output_language=output_language,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Tone adjustment failed: {e}") from e
    return {
        "final_text": final_text,
        "character_validation": validate_both_stages(platform, platform_draft, final_text),
    }
