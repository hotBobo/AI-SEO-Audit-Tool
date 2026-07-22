import urllib.robotparser
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv
import re

# Loads the api keys from .env
load_dotenv(override=False)

def query_perplexity_visibility(target_url: str, keyword_query: str, custom_key: str = None) -> dict:
    '''
    Prompts a search-grounded AI engine to look up a industry query, 
    inspects its citation sources, and reports if the target URL was cited.
    '''
    api_key = custom_key or os.getenv("PERPLEXITY_API_KEY")

    # Return a graceful fallback if the developer hasn't configured a key yet (which I haven't yet lol)
    if not api_key:
        return {
            "engine": "Perplexity Sonar",
            "site_found": False,
            "citations_reviewed": 0,
            "snippet_summary": "API Key missing. Configure PERPLEXITY_API_KEY to activate live AI ranking simulations."
        }
    
    url = "https://api.perplexity.ai/chat/completions"

    # Now we make the actual promts
    payload = {
        "model": "sonar", # Best for web searches
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
    # Give us our credentials
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            ai_data = response.json()
            ai_text = ai_data["choices"][0]["message"]["content"]
            # Perplecity sauce
            citations = ai_data.get("citations", [])
            # Clean up site url to check for basic match (ex. says greenehouse.agency/about_us instead of just greenehouse.agency)
            site_found = any(is_domain_in_text(target_url, source) for source in citations)
            
            
            return {
                "engine": "Perplexity Sonar",
                "site_found": site_found,
                "citations_reviewed": len(citations),
                "snippet_summary": ai_text
            }
    except Exception as e:
        print(f"AI Simulation Error: {e}")
    return {
        "engine": "Perplexity Sonar",
        "site_found": False,
        "citations_reviewed": 0,
        "snippet_summary": "Simulation execution failed or timed out."
    }

def is_domain_in_text(target_url: str, text: str) -> bool:
    """Normalizes the target URL domain to check if it appears in the text."""
    clean_domain = re.sub(r'https?://(www\.)?', '', target_url.lower()).split('/')[0]
    return clean_domain in text.lower() or target_url.lower() in text.lower()

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