import React, { useState, useEffect } from 'react';
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

    const currentSessionId = activeSessionId || Date.now().toString();
    const sessionTimestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setLoading(true);
    setSessions((prev) => {
      if (activeSessionId) {
        return prev.map((s) => s.id === activeSessionId
          ? { ...s, query: q, timestamp: sessionTimestamp, result: null, loading: true }
          : s);
      }

      const tempSession = {
        id: currentSessionId,
        query: q,
        timestamp: sessionTimestamp,
        result: null,
        loading: true,
      };
      return [tempSession, ...prev];
    });
    setActiveSessionId(currentSessionId);
    setQuery('');

    const finish = (result) => setSessions((prev) => prev.map((s) =>
      (s.id === currentSessionId ? { ...s, query: q, timestamp: sessionTimestamp, result, loading: false } : s)));

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
        <div className="w-full max-w-2xl mx-auto mb-8">
          <div className="relative flex items-center bg-[#13151b] border border-zinc-800 hover:border-amber-500/40 focus-within:border-amber-500/80 rounded-xl shadow-2xl transition-all">
            <Search className="w-5 h-5 text-zinc-500 ml-4 flex-shrink-0" />
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleRunResearch()} placeholder="Enter research topic, question, or technology..." className="w-full bg-transparent px-4 py-4 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none" disabled={loading} />
            <button onClick={() => handleRunResearch()} disabled={loading || !query.trim()} className="mr-2 px-5 py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 disabled:opacity-40 text-black font-semibold text-xs rounded-lg transition-all shadow-md flex items-center gap-2"><span>Research</span><ArrowUpRight className="w-4 h-4" /></button>
          </div>
        </div>

        {!activeSession ? <div className="h-full flex flex-col justify-center items-center text-center -mt-8"><div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-400/10 via-amber-500/20 to-amber-600/5 border border-amber-500/30 flex items-center justify-center mb-6 shadow-2xl shadow-amber-500/10"><Sparkles className="w-8 h-8 text-amber-400" /></div><h2 className="font-serif text-3xl md:text-4xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-amber-100 via-amber-200 to-amber-400 mb-3">Autonomous Intelligence Engine</h2><p className="text-sm md:text-base text-zinc-400 max-w-xl mb-10 leading-relaxed font-light">Ask any complex technical, market, or scientific question. The agent autonomously plans search queries, verifies web sources, and drafts cited reports.</p>
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
