import urllib.robotparser
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv
import re
from typing import Optional

# Loads the api keys from .env
load_dotenv(override=False)

def query_ai_visibility(
    engine: str, 
    target_url: str, 
    keyword_query: str, 
    custom_key: Optional[str] = None
) -> dict:
    """
    Unified function to query Perplexity, ChatGPT, Claude, or Gemini for site visibility.
    """
    engine_lower = engine.lower()

    # Match engine to appropriate environment variable
    env_vars = {
        "perplexity": "PERPLEXITY_API_KEY",
        "chatgpt": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY"
    }

    # 1. Resolve API Key
    api_key = custom_key or os.getenv(env_vars.get(engine_lower, ""))
    if not api_key:
        return {
            "engine": engine.capitalize(),
            "site_found": False,
            "citations_reviewed": 0,
            "snippet_summary": f"API Key missing for {engine.capitalize()}."
        }

    raw_text = ""
    citations = []

    try:
        # 2. Switch Statement based on Engine
        match engine_lower:
            case "perplexity":
                url = "https://api.perplexity.ai/chat/completions"
                payload = {
                    "model": "sonar",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an advanced SEO auditing assistant. You must run live searches and strictly report back which websites you cited. Do not use raw markdown syntax or citation markers in your response. Only return plain text."
                        },
                        {
                            "role": "user",
                            "content": f"Search for: '{keyword_query}'. Analyze the top citations and websites you pull back to answer this query. Does the website '{target_url}' appear prominently as a reference or recommendation? Summarize in 2 sentences how visible this site is in your search context."
                        }
                    ]
                }
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                resp = requests.post(url, json=payload, headers=headers, timeout=15).json()
                
                raw_text = resp["choices"][0]["message"]["content"]
                citations = resp.get("citations", [])

            case "chatgpt":
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-5-search-api",
                    web_search_options={},
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an advanced SEO auditing assistant. You must run live searches and strictly report back which websites you cited. Do not use raw markdown syntax or citation markers in your response. Only return plain text."
                        },
                        {
                            "role": "user",
                            "content": f"Search for: '{keyword_query}'. Analyze the top citations and websites you pull back to answer this query. Does the website '{target_url}' appear prominently as a reference or recommendation? Summarize in 2 sentences how visible this site is in your search context."
                        }
                    ]
                )
                raw_text = resp.choices[0].message.content
                # Collect citation annotations if available
                annotations = getattr(resp.choices[0].message, "annotations", [])
                citations = [str(a) for a in annotations]

            case "claude":
                from anthropic import Anthropic
                client = Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model="claude-opus-4-8",
                    max_tokens=500,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an advanced SEO auditing assistant. You must run live searches and strictly report back which websites you cited. Do not use raw markdown syntax or citation markers in your response. Only return plain text."
                        },
                        {
                            "role": "user",
                            "content": f"Search for: '{keyword_query}'. Analyze the top citations and websites you pull back to answer this query. Does the website '{target_url}' appear prominently as a reference or recommendation? Summarize in 2 sentences how visible this site is in your search context."
                        }
                    ],
                    tools=[{"type": "web_search_20250305", "name": "web_search"}]
                )
                for block in resp.content:
                    if hasattr(block, 'text'):
                        raw_text += block.text

            case "gemini":
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=f"You are an advanced SEO auditing assistant. You must run live searches and strictly report back which websites you cited. Do not use raw markdown syntax or citation markers in your response. Only return plain text. Search for: '{keyword_query}'. Analyze the top citations and websites you pull back to answer this query. Does the website '{target_url}' appear prominently as a reference or recommendation? Summarize in 2 sentences how visible this site is in your search context.",
                    config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
                )
                raw_text = resp.text or ""
                # Parse citations out of grounding metadata
                try:
                    for chunk in resp.candidates[0].grounding_metadata.grounding_chunks:
                        if chunk.web and chunk.web.uri:
                            citations.append(chunk.web.uri)
                except Exception:
                    pass

            case "groq":
                from groq import Groq
                client = Groq(api_key=api_key)
                prompt = (
                    f"Search your knowledge context for query: '{keyword_query}'. "
                    f"Does the domain '{target_url}' typically rank as a primary source or top result? "
                    f"Summarize in 2 short sentences."
                )
                resp = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="openai/gpt-oss-120b",  # Free Llama 3.3 70B on Groq
                )
                choice = resp.choices[0]
                raw_text = choice.message.content or ""
                if choice.message.executed_tools:
                    citations = choice.message.executed_tools[0].search_results

            case _:
                return {"engine": engine, "site_found": False, "snippet_summary": f"Unsupported engine '{engine}'."}

        # 3. Unified Post-Processing (Cleaning + Domain Matching)
        cleaned_text = clean_ai_text(raw_text)
        site_found = any(is_domain_in_text(target_url, ref) for ref in citations)

        return {
            "engine": engine.capitalize(),
            "site_found": site_found,
            "citations_reviewed": len(citations),
            "snippet_summary": cleaned_text
        }

    except Exception as e:
            error_msg = str(e).lower()
            print(f"[{engine.upper()}] Simulation Error: {e}")

            # --- FALLBACK CHECK FOR LOW CREDITS / QUOTA EXCEEDED ---
            if any(term in error_msg for term in ["insufficient_quota", "credit", "balance", "429", "quota"]):
                friendly_summary = f"Account out of API credits or rate limited. Provide a funded key to enable {engine.capitalize()}."
            else:
                friendly_summary = f"Execution failed or timed out: {e}"

            return {
                "engine": engine.capitalize(),
                "site_found": False,
                "citations_reviewed": 0,
                "snippet_summary": friendly_summary
            }

def is_domain_in_text(target_url: str, text: str) -> bool:
    """Normalizes the target URL domain to check if it appears in the text."""
    clean_domain = re.sub(r'https?://(www\.)?', '', target_url.lower()).split('/')[0]
    return clean_domain in text.lower() or target_url.lower() in text.lower()

def clean_ai_text(text: str) -> str:
    """Strips markdown bolding and citation footnotes like [1], [2][7]."""
    # Remove markdown bold/italics symbols (* and _)
    cleaned = re.sub(r'[*_]', '', text)
    # Remove citation brackets like [1], [2], [10]
    cleaned = re.sub(r'\[\d+\]', '', cleaned)
    # Clean up double spaces caused by removing brackets
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def fetch_robots_txt(url: str) -> str:
    """
    Safely fetches the robots.txt file from a given base URL.
    Handles redirects and returns an empty string if 404.
    """
    # Standardize the URL: ensure we append /robots.txt to the root domain,
    # not a subdirectory.
    if not url.endswith('/robots.txt'):
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = urljoin(base_url, "/robots.txt")
    else:
        robots_url = url
        
    headers = {'User-Agent': 'AIAuditEngine/1.0 (Educational Bot)'}
    
    try:
        # Fetch the file. Set a timeout so the script doesn't hang indefinitely.
        response = requests.get(robots_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            # Under RFC standards, a 404 means implicit unconditional access for all bots
            print("No robots.txt found (404). All bots have access.")
            return ""
        else:
            print(f"Server responded with status code: {response.status_code}")
            return ""
            
    except requests.RequestException as e:
        print(f"Network error trying to connect to {robots_url}: {e}")
        return ""
    
def check_website_exists(url: str) -> bool:
    '''
    Checks if the website exists in the first place. Returns True if reachable, otherwise False.
    '''
    headers = {'User-Agent': 'AIAuditEngine/1.0 (Educational Bot)'}
    try:
        response = requests.head(url, headers=headers, timeout=10)
        
        # Fallback if a server blocks HEAD requests but is actually online
        if response.status_code in [403, 405]:
            response = requests.get(url, headers=headers, timeout=5, stream=True)
            
        # Deals with successful conection, but blocked site (ex. a page that doesn't exist)
        if response.status_code >= 400:
            print(f"URL is unreachable or returned error code: {response.status_code}")
            return False
        return True
    except requests.RequestException as e:
        # Deals with application not connecting to site
        print(f"Network error trying to connect to {url}: {e}")
        return False

def parse_rules(raw_text: str) -> urllib.robotparser.RobotFileParser:
    """
    Instantiates a RobotFileParser object and parses raw robots.txt data.
    """
    parser = urllib.robotparser.RobotFileParser()
    # splitlines() converts the text block into a list of individual lines
    parser.parse(raw_text.splitlines())
    return parser

def analyze_ai_accessibility(parser: urllib.robotparser.RobotFileParser) -> dict:
    """
    Checks accessibility for distinct training and search AI bots on the home path (/).
    """
    ai_bots = {
        "Search & Discovery (Should be ALLOWED for SEO)": [
            "OAI-SearchBot",       # ChatGPT's search engine
            "Claude-SearchBot",    # Anthropic's search engine
            "PerplexityBot"        # Perplexity's indexer
        ],
        "Model Training (Can be BLOCKED to protect IP)": [
            "GPTBot",              # OpenAI's training model
            "ClaudeBot",           # Anthropic's training model
            "Google-Extended",     # Google Gemini's training token
            "Applebot-Extended"    # Apple's training model
        ]
    }
    
    report = {}
    
    # We loop through our bots and ask the parser state machine if they can fetch '/'
    for category, bots in ai_bots.items():
        report[category] = {}
        for bot in bots:
            # can_fetch returns True if allowed, False if blocked
            is_allowed = parser.can_fetch(bot, "/")
            report[category][bot] = "ALLOWED" if is_allowed else "BLOCKED"
            
    return report

if __name__ == "__main__":
    target_site = "https://www.eternalpaws.com/"
    
    print(f"Fetching robots.txt for: {target_site}...")
    raw_data = fetch_robots_txt(target_site)
    
    # Even if raw_data is empty (like a 404), we can parse it to get default 'ALLOW' rules
    parser = parse_rules(raw_data)
    analysis = analyze_ai_accessibility(parser)
    
    # Print the final dictionary as formatted JSON so it looks beautiful in the terminal
    import json
    print("\n--- AI Accessibility Report ---")
    print(json.dumps(analysis, indent=4))


def analyze_html_structure(url: str) -> dict:
    """
    Fetches the main HTML of the page and scans it for Schema Markup 
    and Conversational FAQ Heading structures.
    """
    headers = {'User-Agent': 'AIAuditEngine/1.0 (Educational Bot)'}
    report = {
        "schema_markup": {
            "found": False,
            "types_detected": [],
            "status": "MISSING (Highly Recommended for AI Discovery)"
        },
        "conversational_headings": {
            "count": 0,
            "examples": [],
            "status": "POOR (Add H2/H3 questions like 'How' or 'Where')"
        }
    }

    try:
        # 1. Fetch the raw HTML content of the homepage
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return report
        
        # 2. Load the HTML into the BeautifulSoup DOM parser
        soup = BeautifulSoup(response.text, 'html.parser')

        # --- Pilllar A: Scan for JSON-LD Schema Markup ---
        # Schema is almost always embedded inside <script type="application/ld+json"> tags
        schema_tags = soup.find_all('script', type='application/ld+json')
        
        if schema_tags:
            report["schema_markup"]["found"] = True
            report["schema_markup"]["status"] = "OPTIMIZED (Structured data detected)"
            
            for tag in schema_tags:
                try:
                    # Parse the string inside the script tag as JSON
                    schema_json = json.loads(tag.string)
                    
                    # Schema data can be a single dict or a list of dicts
                    if isinstance(schema_json, dict):
                        if "@type" in schema_json:
                            report["schema_markup"]["types_detected"].append(schema_json["@type"])
                    elif isinstance(schema_json, list):
                        for item in schema_json:
                            if isinstance(item, dict) and "@type" in item:
                                report["schema_markup"]["types_detected"].append(item["@type"])
                except Exception:
                    # If a site has malformed JSON in their schema, skip it gracefully
                    continue

        # --- Pillar B: Scan for Conversational Headings ---
        # Look for H2 and H3 tags that begin with interrogative question words
        question_words = ("how", "what", "where", "why", "can", "is", "who", "when")
        headings = soup.find_all(['h2', 'h3'])
        
        for h in headings:
            text = h.get_text().strip().lower()
            if text.startswith(question_words) or text.endswith('?'):
                report["conversational_headings"]["count"] += 1
                if len(report["conversational_headings"]["examples"]) < 3:
                    # Save a few examples to show the user in the UI report
                    report["conversational_headings"]["examples"].append(h.get_text().strip())

        # Update conversational health status based on count metrics
        count = report["conversational_headings"]["count"]
        if count >= 4:
            report["conversational_headings"]["status"] = "EXCELLENT (Rich conversational hierarchy)"
        elif 1 <= count < 4:
            report["conversational_headings"]["status"] = "MODERATE (Add more direct Q&A headers)"

    except Exception as e:
        print(f"Error extracting HTML elements: {e}")
        
    return report