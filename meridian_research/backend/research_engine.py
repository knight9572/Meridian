import os
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
