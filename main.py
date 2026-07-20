import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from analyzer import fetch_robots_txt, parse_rules, analyze_ai_accessibility, analyze_html_structure

app = FastAPI(
    title="AI SEO Audit API",
    description="An API to evaluate a website's visibility to AI search crawlers.",
    version="1.0.0"
)

app = app

# --- 1. Serve our Static HTML UI Page on the Root Route (/) ---
@app.get("/", response_class=HTMLResponse)
def read_root():
    """
    Serves the custom index.html frontend interface.
    """
    # Find the path to index.html relative to this file
    html_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        # Graceful fallback if index.html is missing
        return HTMLResponse(
            content="<h1>Frontend file index.html not found!</h1>", 
            status_code=404
        )


# --- 2. Keep the Backend JSON API endpoint (/audit) ---
# Update your import line at the top to include our new function

@app.get("/audit")
def run_audit(url: str = Query(..., description="The full URL of the website to audit")):
    # Clean up any accidental leading/trailing whitespace the user might have inputted
    url = url.strip()

    # Smart Protocol Auto-Correction:
    # If the user didn't provide a protocol, we assume modern https:// first
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    # We invoke the network call to fetch the robots.txt file
    raw_data = fetch_robots_txt(url)
    
    # Fallback Mechanism:
    # If our automated https:// attempt completely failed (e.g. SSL/TLS error on an old site),
    # we automatically try a legacy plain http:// fallback before giving up.
    if not raw_data and url.startswith("https://"):
        fallback_url = url.replace("https://", "http://", 1)
        raw_data = fetch_robots_txt(fallback_url)
        if raw_data:
            url = fallback_url # Update our tracking URL if fallback worked

    # If both attempts returned nothing (e.g., completely invalid domain or offline site)
    if not raw_data:
        # Check if the robots file was missing (404) or if the whole site is unreachable
        # If it was a clean 404, fetch_robots_txt returns an empty string but handles it.
        # Let's verify our parser rules can still evaluate it safely.
        pass

    parser = parse_rules(raw_data)
    crawler_report = analyze_ai_accessibility(parser)
    html_report = analyze_html_structure(url)
    
    return {
        "target_url": url,
        "crawler_accessibility": crawler_report,
        "content_structure": html_report
    }