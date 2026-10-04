import os
import sys
import getpass
import subprocess
import time
import shutil
from pathlib import Path


def check_prerequisites():
    print("🔍 Checking prerequisites...")
    if shutil.which("node") is None or shutil.which("npm") is None:
        print("❌ Node.js and npm are required. Please install Node.js from https://nodejs.org")
        sys.exit(1)
    print("✅ Prerequisites found: Node.js, npm, Python 3.\n")


def write_file(path, content):
    path = Path(path)
    os.makedirs(path.parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  📝 Generated {path}")


def read_existing_env(env_path):
    values = {}
    if Path(env_path).exists():
        for line in Path(env_path).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def get_key(name, existing, prompt):
    """Priority: environment variable > existing .env > hidden prompt."""
    val = os.environ.get(name) or existing.get(name, "")
    if val:
        print(f"  🔑 Using {name} from {'environment' if os.environ.get(name) else '.env'}")
        return val
    return getpass.getpass(prompt).strip()


def main():
    print("=" * 60)
    print("✨ MERIDIAN AI RESEARCH AGENT - ALL-IN-ONE SETUP SCRIPT")
    print("=" * 60)
    check_prerequisites()

    base_dir = Path(__file__).parent.resolve() / "meridian_research"
    os.makedirs(base_dir, exist_ok=True)
    print(f"📁 Unpacking full application into: {base_dir}\n")

    backend_dir = base_dir / "backend"
    frontend_dir = base_dir / "frontend"
    src_dir = frontend_dir / "src"

    existing_env = read_existing_env(backend_dir / ".env")
    openai_key = get_key(
        "OPENAI_API_KEY", existing_env,
        "Enter OpenAI API Key (hidden, Enter to skip): ",
    )
    tavily_key = get_key(
        "TAVILY_API_KEY", existing_env,
        "Enter Tavily API Key (hidden, Enter to use DuckDuckGo/Wikipedia): ",
    )
    openai_model = os.environ.get("OPENAI_MODEL") or existing_env.get("OPENAI_MODEL") or "gpt-4o-mini"

    write_file(backend_dir / "requirements.txt", r'''fastapi>=0.115.0
uvicorn>=0.34.0
pydantic>=2.7.4
httpx>=0.28.1
openai>=1.40.0
python-dotenv>=1.0.1
beautifulsoup4>=4.12.0
''')

    env_path = backend_dir / ".env"
    write_file(env_path, f"OPENAI_API_KEY={openai_key}\nTAVILY_API_KEY={tavily_key}\nOPENAI_MODEL={openai_model}\n")
    try:
        os.chmod(env_path, 0o600)
    except Exception:
        pass

    write_file(base_dir / ".gitignore", r'''.env
**/.env
node_modules/
__pycache__/
dist/
''')

    write_file(backend_dir / "research_engine.py", r'''import os
import re
import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

MAX_SOURCES_TO_READ = 4
MAX_CHARS_PER_PAGE = 6000


def clean_html(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def search_tavily(query: str):
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
            json={"query": query, "max_results": 6, "search_depth": "basic"},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                for r in data.get("results", [])
            ]
        print(f"Tavily returned status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"Tavily search error: {e}")
    return []


def search_duckduckgo(query: str):
    try:
        resp = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=12,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for r in soup.select(".result")[:6]:
                link = r.select_one(".result__a")
                snippet = r.select_one(".result__snippet")
                if link and snippet:
                    href = link.get("href", "")
                    m = re.search(r"uddg=([^&]+)", href)
                    if m:
                        href = urllib.parse.unquote(m.group(1))
                    elif href.startswith("//"):
                        href = "https:" + href
                    results.append({
                        "title": link.get_text(strip=True),
                        "url": href,
                        "snippet": snippet.get_text(strip=True),
                    })
            if results:
                return results
        else:
            print(f"DuckDuckGo returned status {resp.status_code} (possible bot check)")
    except Exception as e:
        print(f"DuckDuckGo search error: {e}")
    return []


def search_wikipedia(query: str):
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "format": "json", "srlimit": 5, "srsearch": query},
            headers={"User-Agent": "MeridianAgent/1.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get("query", {}).get("search", []):
                snippet = BeautifulSoup(item.get("snippet", ""), "html.parser").get_text()
                title = item.get("title", "")
                results.append({
                    "title": title,
                    "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                    "snippet": snippet,
                })
            return results
    except Exception as e:
        print(f"Wikipedia search error: {e}")
    return []


def web_search(query: str):
    if TAVILY_API_KEY:
        res = search_tavily(query)
        if res:
            return res
    res = search_duckduckgo(query)
    if res:
        return res
    return search_wikipedia(query)


def read_page(url: str):
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
        content_type = resp.headers.get("content-type", "")
        if resp.status_code == 200 and "html" in content_type.lower():
            return clean_html(resp.text)[:MAX_CHARS_PER_PAGE]
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return ""


def normalize_finding(f) -> str:
    """Models occasionally return objects instead of plain strings."""
    if isinstance(f, str):
        return f
    if isinstance(f, dict):
        for key in ("finding", "text", "detail", "description", "summary"):
            if isinstance(f.get(key), str):
                title = f.get("title") or f.get("heading")
                return f"{title}: {f[key]}" if isinstance(title, str) else f[key]
        return json.dumps(f, ensure_ascii=False)
    return str(f)


def build_fallback(query, sources, tool_logs, error=None):
    out = {
        "bottom_line": f"Collected {len(sources)} sources for '{query}'. "
                       + ("Add an OpenAI API key for a synthesized report." if error is None else "Synthesis failed; showing raw snippets."),
        "findings": [s.get("snippet") or s.get("title", "") for s in sources[:5] if s.get("snippet") or s.get("title")],
        "sources": sources,
        "tool_logs": tool_logs,
    }
    if error:
        out["error"] = error
    return out


def run_agent_research(query: str):
    tool_logs = [{"step": "Plan", "detail": f"Formulating search for: '{query}'"}]

    sources = web_search(query)
    tool_logs.append({"step": "Web Search", "detail": f"Found {len(sources)} sources"})

    to_read = [s for s in sources[:MAX_SOURCES_TO_READ] if s.get("url")]
    contents = {}
    if to_read:
        with ThreadPoolExecutor(max_workers=len(to_read)) as pool:
            for s, text in zip(to_read, pool.map(lambda s: read_page(s["url"]), to_read)):
                contents[s["url"]] = text
                tool_logs.append({
                    "step": "Read Page",
                    "detail": f"{'Read' if text else 'Could not read'} {s['url']}",
                })

    blocks = []
    for i, s in enumerate(sources, start=1):
        body = contents.get(s.get("url")) or s.get("snippet", "")
        blocks.append(f"SOURCE [{i}] {s.get('title', '')} | {s.get('url', '')}\n{body}\n")
    context_str = "\n".join(blocks)

    if not sources:
        return build_fallback(query, sources, tool_logs, error="No search results were found.")

    if not client:
        return build_fallback(query, sources, tool_logs)

    prompt = f"""You are Meridian, an elite research analyst.
User Query: "{query}"

Numbered web sources:
{context_str}

Write an authoritative, well-grounded research report using ONLY the sources above.
Cite with bracketed source numbers like [1] or [2][3] that match the SOURCE numbers.
Respond STRICTLY with a JSON object:
{{
  "bottom_line": "1-2 sentence core conclusion",
  "findings": ["each finding is a plain string with inline citations like [1]", "..."]
}}
Provide 4-6 findings. Every finding must be a string, not an object.
"""
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional research agent that only outputs valid JSON."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(response.choices[0].message.content)
        findings = [normalize_finding(f) for f in (data.get("findings") or [])]
        tool_logs.append({"step": "Synthesize", "detail": f"Report generated with {OPENAI_MODEL}"})
        return {
            "bottom_line": normalize_finding(data.get("bottom_line", "")),
            "findings": findings,
            "sources": sources,
            "tool_logs": tool_logs,
            "model": OPENAI_MODEL,
        }
    except Exception as e:
        tool_logs.append({"step": "Synthesize", "detail": f"Failed: {e}"})
        return build_fallback(query, sources, tool_logs, error=str(e))
''')

    write_file(backend_dir / "main.py", r'''from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from research_engine import run_agent_research, OPENAI_MODEL, client

app = FastAPI(title="Meridian Research Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResearchQuery(BaseModel):
    query: str


@app.post("/api/research")
def handle_research(req: ResearchQuery):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    print(f"⚡ [Research Request] Query: {query}")
    try:
        result = run_agent_research(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok", "data": result}


@app.get("/api/health")
def health():
    return {"status": "running", "model": OPENAI_MODEL, "llm_enabled": client is not None}
''')

    write_file(frontend_dir / "package.json", r'''{
  "name": "meridian-research-ui",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
  "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1", "lucide-react": "^0.378.0"},
  "devDependencies": {"@vitejs/plugin-react": "^4.3.0", "autoprefixer": "^10.4.19", "postcss": "^8.4.38", "tailwindcss": "^3.4.3", "vite": "^5.2.11"}
}''')

    write_file(frontend_dir / "vite.config.js", r'''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 }
})''')

    write_file(frontend_dir / "index.html", r'''<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Meridian — Autonomous AI Research Agent</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  </head>
  <body class="bg-[#0b0c0e] text-[#ededee] font-sans antialiased selection:bg-amber-500/20 selection:text-amber-300">
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>''')

    write_file(frontend_dir / "tailwind.config.js", r'''export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: { serif: ['Cinzel', 'serif'], sans: ['Inter', 'sans-serif'] },
    },
  },
  plugins: [],
}''')

    write_file(frontend_dir / "postcss.config.js", r'''export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
}''')

    write_file(src_dir / "index.css", r'''@tailwind base;
@tailwind components;
@tailwind utilities;

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #27272a; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #3f3f46; }
''')

    write_file(src_dir / "main.jsx", r'''import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>,
)''')

    write_file(src_dir / "App.jsx", r'''import React, { useState, useEffect } from 'react';
import {
  Sparkles, Search, Compass, BookOpen, ExternalLink, ChevronDown,
  ChevronRight, Plus, Trash2, ArrowUpRight, Copy, Check, Terminal, Globe
} from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const STORAGE_KEY = 'meridian_sessions';
const SUGGESTIONS = [
  "Latest breakthroughs in solid-state battery commercialization",
  "How will quantum computing impact RSA-4096 cryptography by 2030?",
  "Comparison of modern vector database architectures (pgvector vs Milvus)",
  "Autonomous AI agent frameworks: LangGraph vs AutoGen vs CrewAI"
];
const asText = (v) => (typeof v === 'string' ? v : JSON.stringify(v));

function CitedText({ text, sources }) {
  const parts = asText(text).split(/(\[\d+\])/g);
  return <>{parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (!m) return <React.Fragment key={i}>{part}</React.Fragment>;
    const src = sources?.[Number(m[1]) - 1];
    if (!src?.url) return <React.Fragment key={i}>{part}</React.Fragment>;
    return <a key={i} href={src.url} target="_blank" rel="noopener noreferrer" title={src.title}
      className="text-amber-400 hover:text-amber-300 font-semibold align-super text-[10px] mx-0.5 no-underline">{part}</a>;
  })}</>;
}

function loadSessions() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    return raw.map((s) => s.loading ? { ...s, loading: false, result: {
      bottom_line: 'This research session was interrupted before it finished.',
      findings: ['Run the query again to retry.'], sources: [],
    }} : s);
  } catch { return []; }
}

export default function App() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState(loadSessions);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [showLogs, setShowLogs] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.filter((s) => !s.loading))); }
    catch { /* storage may be full or unavailable */ }
  }, [sessions]);

  const activeSession = sessions.find((s) => s.id === activeSessionId) || null;
  const modelLabel = activeSession?.result?.model || 'LLM + Web Tools';
  const handleRunResearch = async (searchQuery) => {
    const q = (typeof searchQuery === 'string' ? searchQuery : query).trim();
    if (!q || loading) return;
    setLoading(true);
    const newSessionId = Date.now().toString();
    const tempSession = { id: newSessionId, query: q,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), result: null, loading: true };
    setSessions((prev) => [tempSession, ...prev]);
    setActiveSessionId(newSessionId);
    setQuery('');
    const finish = (result) => setSessions((prev) => prev.map((s) =>
      (s.id === newSessionId ? { ...s, result, loading: false } : s)));
    try {
      const resp = await fetch(`${API_URL}/api/research`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: q }) });
      if (!resp.ok) {
        let detail = `Server responded with ${resp.status}`;
        try { const err = await resp.json(); if (err.detail) detail = asText(err.detail); } catch { /* ignore */ }
        throw new Error(detail);
      }
      const data = await resp.json();
      finish(data.data);
    } catch (err) {
      console.error(err);
      finish({ bottom_line: 'The research request failed.',
        findings: [`${err.message}. Make sure the FastAPI backend is running on ${API_URL}.`], sources: [] });
    } finally { setLoading(false); }
  };
  const deleteSession = (id, e) => {
    e.stopPropagation();
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeSessionId === id) setActiveSessionId(null);
  };
  const copyMarkdown = async () => {
    if (!activeSession?.result) return;
    const { bottom_line, findings = [], sources = [] } = activeSession.result;
    const md = `# Research Report: ${activeSession.query}\n\n## Bottom Line\n${asText(bottom_line)}\n\n## Key Findings\n${findings.map((f, i) => `${i + 1}. ${asText(f)}`).join('\n')}\n\n## Sources\n${sources.map((s, i) => `[${i + 1}] [${s.title}](${s.url})`).join('\n')}`;
    try { await navigator.clipboard.writeText(md); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch (e) { console.error('Clipboard unavailable', e); }
  };

  return <div className="flex h-screen w-full bg-[#0b0c0e] text-[#ededee]">
    <aside className="w-72 border-r border-[#1f2128] bg-[#0e1014] flex flex-col">
      <div className="p-4 border-b border-[#1f2128] flex items-center justify-between">
        <div className="flex items-center gap-2.5"><div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-amber-700 flex items-center justify-center text-black font-bold shadow-lg shadow-amber-500/20"><Compass className="w-5 h-5 text-black" /></div><div><h1 className="font-serif font-bold tracking-wider text-sm text-amber-200">MERIDIAN</h1><p className="text-[10px] text-zinc-500 tracking-wider">RESEARCH AGENT</p></div></div>
        <button onClick={() => setActiveSessionId(null)} className="p-1.5 hover:bg-zinc-800 rounded-md text-zinc-400 hover:text-white transition-colors" title="New Research"><Plus className="w-4 h-4" /></button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-1"><div className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider px-2 py-1">History</div>
        {sessions.length === 0 ? <div className="text-xs text-zinc-600 px-2 py-4 italic">No past sessions yet</div> : sessions.map((s) => <div key={s.id} onClick={() => setActiveSessionId(s.id)} className={`group flex items-center justify-between px-3 py-2.5 rounded-lg text-xs cursor-pointer transition-all ${activeSessionId === s.id ? 'bg-amber-500/10 text-amber-300 border border-amber-500/30' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'}`}>
          <div className="truncate flex-1 pr-2"><p className="font-medium truncate">{s.query}</p><p className="text-[10px] text-zinc-500">{s.timestamp}</p></div><button onClick={(e) => deleteSession(s.id, e)} className="opacity-0 group-hover:opacity-100 hover:text-red-400 p-1 rounded"><Trash2 className="w-3.5 h-3.5" /></button>
        </div>)}
      </div><div className="p-3 border-t border-[#1f2128] text-[11px] text-zinc-500 flex items-center justify-between"><span>Engine: {modelLabel}</span><span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span></div>
    </aside>
    <main className="flex-1 flex flex-col overflow-hidden bg-gradient-to-b from-[#0b0c0e] to-[#07080a]">
      <header className="h-14 border-b border-[#1f2128] px-6 flex items-center justify-between bg-[#0b0c0e]/80 backdrop-blur-md"><div className="flex items-center gap-2 text-xs text-zinc-400"><Globe className="w-4 h-4 text-amber-400" /><span>Autonomous Web Retrieval &amp; Synthesis</span></div>{activeSession?.result && <button onClick={copyMarkdown} className="flex items-center gap-1.5 text-xs bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-white px-3 py-1.5 rounded-lg border border-zinc-800 transition-colors">{copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}<span>{copied ? 'Copied' : 'Export Markdown'}</span></button>}</header>
      <div className="flex-1 overflow-y-auto p-6 md:p-10 max-w-5xl mx-auto w-full">
        {!activeSession ? <div className="h-full flex flex-col justify-center items-center text-center -mt-8"><div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-400/10 via-amber-500/20 to-amber-600/5 border border-amber-500/30 flex items-center justify-center mb-6 shadow-2xl shadow-amber-500/10"><Sparkles className="w-8 h-8 text-amber-400" /></div><h2 className="font-serif text-3xl md:text-4xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-amber-100 via-amber-200 to-amber-400 mb-3">Autonomous Intelligence Engine</h2><p className="text-sm md:text-base text-zinc-400 max-w-xl mb-10 leading-relaxed font-light">Ask any complex technical, market, or scientific question. The agent autonomously plans search queries, verifies web sources, and drafts cited reports.</p>
          <div className="w-full max-w-2xl mb-8"><div className="relative flex items-center bg-[#13151b] border border-zinc-800 hover:border-amber-500/40 focus-within:border-amber-500/80 rounded-xl shadow-2xl transition-all"><Search className="w-5 h-5 text-zinc-500 ml-4 flex-shrink-0" /><input type="text" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleRunResearch()} placeholder="Enter research topic, question, or technology..." className="w-full bg-transparent px-4 py-4 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none" disabled={loading} /><button onClick={() => handleRunResearch()} disabled={loading || !query.trim()} className="mr-2 px-5 py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 disabled:opacity-40 text-black font-semibold text-xs rounded-lg transition-all shadow-md flex items-center gap-2"><span>Research</span><ArrowUpRight className="w-4 h-4" /></button></div></div>
          <div className="w-full max-w-2xl"><p className="text-xs text-zinc-500 mb-3 uppercase tracking-wider font-semibold">Or explore suggested prompts</p><div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">{SUGGESTIONS.map((s, idx) => <button key={idx} onClick={() => handleRunResearch(s)} className="text-left p-3.5 rounded-xl bg-[#121419] hover:bg-[#1a1c24] border border-zinc-800/80 hover:border-amber-500/30 text-xs text-zinc-300 hover:text-amber-200 transition-all group flex items-start justify-between gap-2"><span className="line-clamp-2">{s}</span><ArrowUpRight className="w-4 h-4 text-zinc-600 group-hover:text-amber-400 flex-shrink-0 transition-colors" /></button>)}</div></div>
        </div> : <div className="space-y-6 pb-20"><div className="border-b border-[#1f2128] pb-6"><div className="flex items-center gap-2 text-amber-400 text-xs font-semibold uppercase tracking-wider mb-2"><Sparkles className="w-4 h-4" /> Research Query</div><h1 className="text-2xl md:text-3xl font-serif font-bold text-white tracking-wide">{activeSession.query}</h1></div>
          {activeSession.loading ? <div className="p-8 rounded-2xl bg-[#121419] border border-zinc-800 flex flex-col items-center justify-center space-y-4"><div className="w-10 h-10 border-2 border-amber-500/20 border-t-amber-400 rounded-full animate-spin"></div><div className="text-center"><p className="text-sm font-medium text-zinc-200">Autonomous Agent at Work</p><p className="text-xs text-zinc-500 mt-1">Executing web queries, reading page contents, and cross-referencing findings...</p></div></div> : activeSession.result && <>
            <div className="p-6 rounded-2xl bg-gradient-to-r from-amber-500/10 via-[#14161d] to-[#14161d] border border-amber-500/30 shadow-xl"><h3 className="text-xs font-bold uppercase tracking-widest text-amber-400 mb-2">Executive Summary</h3><p className="text-base text-zinc-200 leading-relaxed font-light"><CitedText text={activeSession.result.bottom_line} sources={activeSession.result.sources} /></p>{activeSession.result.error && <p className="mt-3 text-xs text-red-400/80">Note: {activeSession.result.error}</p>}</div>
            {activeSession.result.tool_logs && <div className="rounded-xl border border-zinc-800 bg-[#101216] overflow-hidden"><button onClick={() => setShowLogs(!showLogs)} className="w-full px-5 py-3 flex items-center justify-between text-xs text-zinc-400 hover:text-zinc-200 transition-colors"><span className="flex items-center gap-2"><Terminal className="w-4 h-4 text-amber-400" /><span>Tool Execution Steps ({activeSession.result.tool_logs.length})</span></span>{showLogs ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</button>{showLogs && <div className="p-4 border-t border-zinc-800 bg-[#0d0e12] space-y-2 font-mono text-[11px]">{activeSession.result.tool_logs.map((log, i) => <div key={i} className="flex items-start gap-2 text-zinc-400"><span className="text-amber-400 font-semibold">[{log.step}]</span><span className="break-all">{log.detail}</span></div>)}</div>}</div>}
            <div className="p-6 rounded-2xl bg-[#121419] border border-zinc-800/90 shadow-lg"><h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 mb-4 flex items-center gap-2"><BookOpen className="w-4 h-4 text-amber-400" /> Key Findings &amp; Analysis</h3><div className="space-y-3">{activeSession.result.findings?.map((finding, idx) => <div key={idx} className="flex items-start gap-3 text-sm text-zinc-300 leading-relaxed"><span className="flex-shrink-0 w-6 h-6 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center justify-center text-xs font-bold mt-0.5">{idx + 1}</span><span className="pt-0.5"><CitedText text={finding} sources={activeSession.result.sources} /></span></div>)}</div></div>
            {activeSession.result.sources?.length > 0 && <div className="p-6 rounded-2xl bg-[#121419] border border-zinc-800/90 shadow-lg"><h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 mb-4 flex items-center gap-2"><Globe className="w-4 h-4 text-amber-400" /> Sources ({activeSession.result.sources.length})</h3><div className="grid grid-cols-1 md:grid-cols-2 gap-3">{activeSession.result.sources.map((src, idx) => <a key={idx} href={src.url} target="_blank" rel="noopener noreferrer" className="p-4 rounded-xl bg-[#171920] hover:bg-[#1d2029] border border-zinc-800 hover:border-amber-500/40 transition-all group flex flex-col justify-between"><div><div className="flex items-start justify-between gap-2"><h4 className="text-xs font-semibold text-zinc-200 group-hover:text-amber-300 line-clamp-1">[{idx + 1}] {src.title || 'Source Document'}</h4><ExternalLink className="w-3.5 h-3.5 text-zinc-500 group-hover:text-amber-400 flex-shrink-0" /></div><p className="text-[11px] text-zinc-500 truncate mt-1">{src.url}</p>{src.snippet && <p className="text-xs text-zinc-400 mt-2 line-clamp-2 leading-relaxed font-light">{src.snippet}</p>}</div></a>)}</div></div>}
          </>}
        </div>}
      </div>
    </main>
  </div>;
}
''')

    npm_cmd = shutil.which("npm")
    print("\n📦 Installing Backend dependencies (pip)...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(backend_dir / "requirements.txt")],
        check=True,
    )
    print("\n📦 Installing Frontend dependencies (npm)...")
    subprocess.run([npm_cmd, "install"], cwd=str(frontend_dir), check=True)

    print("\n🚀 Starting Backend server on http://localhost:8000...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"],
        cwd=str(backend_dir),
    )
    time.sleep(2)
    print("🚀 Starting Frontend Vite server on http://localhost:5173...")
    frontend_proc = subprocess.Popen([npm_cmd, "run", "dev"], cwd=str(frontend_dir))

    print("\n" + "=" * 60)
    print("✨ SUCCESS! Meridian Research Agent is running!")
    print("🌐 Open in your browser: http://localhost:5173")
    print("🩺 Backend health check:  http://localhost:8000/api/health")
    print("🛑 Press Ctrl+C in this terminal to stop both servers.")
    print("=" * 60 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down servers...")
        for proc in (backend_proc, frontend_proc):
            proc.terminate()
        for proc in (backend_proc, frontend_proc):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("✅ Shutdown complete.")


if __name__ == "__main__":
    main()
