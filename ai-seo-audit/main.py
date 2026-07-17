import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from analyzer import fetch_robots_txt, parse_rules, analyze_ai_accessibility, analyze_html_structure

app = FastAPI(
    title="AI SEO Audit API",
    description="An API to evaluate a website's visibility to AI search crawlers.",
    version="1.0.0"
)

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
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(
            status_code=400, 
            detail="Invalid URL format. URL must start with 'http://' or 'https://'"
        )

    # Pillar 1: Crawl Accessibility Rules
    raw_data = fetch_robots_txt(url)
    parser = parse_rules(raw_data)
    crawler_report = analyze_ai_accessibility(parser)
    
    # Pillar 2: Deep Content & HTML Inspection
    html_report = analyze_html_structure(url)
    
    # Combine everything into a master response payload
    return {
        "target_url": url,
        "crawler_accessibility": crawler_report,
        "content_structure": html_report
    }