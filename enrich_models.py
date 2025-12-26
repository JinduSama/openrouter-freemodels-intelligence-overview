import json
import os
import httpx
import pandas as pd
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from thefuzz import fuzz, process

# Constants
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
ARTIFICIAL_ANALYSIS_URL = "https://artificialanalysis.ai/leaderboards/models"
CACHE_DIR = Path("cache")
ALIASES_FILE = Path("model_aliases.json")
REPORT_FILE = Path("free_models_report.md")
HTML_REPORT_FILE = Path("free_models_report.html")

def fetch_openrouter_free_models():
    """Fetch models from OpenRouter and filter for free ones."""
    cache_file = CACHE_DIR / "openrouter_models.json"
    
    if cache_file.exists():
        print("Loading OpenRouter models from cache...")
        with open(cache_file, "r") as f:
            data = json.load(f)
    else:
        print("Fetching OpenRouter models from API...")
        response = httpx.get(OPENROUTER_MODELS_URL)
        response.raise_for_status()
        data = response.json()
        CACHE_DIR.mkdir(exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)
    
    free_models = []
    for model in data.get("data", []):
        pricing = model.get("pricing", {})
        # Check if all pricing fields are "0"
        is_free = all(str(v) == "0" for v in pricing.values())
        if is_free:
            free_models.append({
                "id": model.get("id"),
                "name": model.get("name"),
                "context_length": model.get("context_length"),
                "description": model.get("description")
            })
    
    print(f"Found {len(free_models)} free models on OpenRouter.")
    return free_models

def scrape_artificial_analysis():
    """Scrape Artificial Analysis leaderboard using Playwright."""
    cache_file = CACHE_DIR / "artificial_analysis_leaderboard.json"
    
    if cache_file.exists():
        print("Loading Artificial Analysis data from cache...")
        with open(cache_file, "r") as f:
            return json.load(f)
    
    print("Scraping Artificial Analysis leaderboard...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(ARTIFICIAL_ANALYSIS_URL)
        page.wait_for_selector("table")
        
        # Expand columns to get all metrics
        expand_button = page.get_by_role("button", name="Expand Columns")
        if expand_button.is_visible():
            expand_button.click()
            page.wait_for_timeout(2000)
        
        content = page.content()
        browser.close()
    
    soup = BeautifulSoup(content, "html.parser")
    table = soup.find("table")
    if not table:
        print("Error: Could not find table on Artificial Analysis.")
        return []
    
    thead = table.find("thead")
    header_rows = thead.find_all("tr")
    if len(header_rows) < 2:
        print("Error: Unexpected table header structure.")
        return []
    
    # Use the second header row for column names
    headers = [th.get_text(strip=True) for th in header_rows[1].find_all(["th", "td"])]
    
    data = []
    tbody = table.find("tbody")
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) != len(headers):
            continue
        
        row_dict = {}
        for header, cell in zip(headers, cells):
            row_dict[header] = cell.get_text(strip=True)
        data.append(row_dict)
    
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"Scraped {len(data)} models from Artificial Analysis.")
    return data

def normalize_name(name):
    """Normalize model name for better matching."""
    if not name:
        return ""
    
    # Lowercase
    name = name.lower()
    
    # Remove provider prefix if present (e.g., "Google: ", "Meta: ")
    if ":" in name:
        name = name.split(":", 1)[1].strip()
    
    # Remove common suffixes
    suffixes = [
        "instruct", "chat", "it", "v1", "v2", "v3", "v4", 
        "(free)", "free", "experimental", "exp", "preview",
        "thinking", "think", "coder", "vl"
    ]
    
    # Remove punctuation and extra whitespace
    import re
    name = re.sub(r"[^a-z0-9\s\.]", " ", name)
    
    # Remove suffixes as whole words
    for suffix in suffixes:
        name = re.sub(rf"\b{suffix}\b", "", name)
    
    # Collapse whitespace
    name = " ".join(name.split())
    
    return name

def match_models(free_models, aa_data):
    """Match OpenRouter models with Artificial Analysis data."""
    # Load aliases
    aliases = {}
    if ALIASES_FILE.exists():
        with open(ALIASES_FILE, "r") as f:
            aliases = json.load(f)
    
    # Prepare AA data for matching
    aa_df = pd.DataFrame(aa_data)
    aa_names = aa_df["Model"].tolist()
    aa_norm_map = {normalize_name(name): name for name in aa_names}
    
    matched_results = []
    
    for or_model in free_models:
        or_id = or_model["id"]
        or_name = or_model["name"]
        
        match_found = False
        aa_row = None
        match_type = "unmatched"
        
        # 1. Check aliases
        if or_id in aliases:
            alias_name = aliases[or_id]
            aa_row = aa_df[aa_df["Model"] == alias_name]
            if not aa_row.empty:
                match_found = True
                match_type = "alias"
        
        # 2. Exact match (normalized)
        if not match_found:
            norm_or_name = normalize_name(or_name)
            if norm_or_name in aa_norm_map:
                aa_name = aa_norm_map[norm_or_name]
                aa_row = aa_df[aa_df["Model"] == aa_name]
                match_found = True
                match_type = "exact (norm)"
        
        # 3. Fuzzy match
        if not match_found:
            # Use a high threshold as per plan
            best_match, score = process.extractOne(or_name, aa_names, scorer=fuzz.token_sort_ratio)
            if score >= 90:
                aa_row = aa_df[aa_df["Model"] == best_match]
                match_found = True
                match_type = f"fuzzy ({score})"
        
        result = or_model.copy()
        if match_found and aa_row is not None:
            # Merge AA data
            aa_dict = aa_row.iloc[0].to_dict()
            # Remove redundant columns
            aa_dict.pop("Model", None)
            aa_dict.pop("Creator", None)
            aa_dict.pop("ContextWindow", None)
            result.update(aa_dict)
            result["match_status"] = match_type
        else:
            result["match_status"] = "unmatched"
            
        matched_results.append(result)
    
    return matched_results

def generate_report(matched_results):
    """Generate Markdown and HTML reports from matched results."""
    df = pd.DataFrame(matched_results)
    
    # Define base columns
    base_cols = ["id", "name", "context_length", "match_status"]
    
    # Identify metric columns (everything else except description)
    all_cols = df.columns.tolist()
    metric_cols = [c for c in all_cols if c not in base_cols and c != "description"]
    
    # Sort metric columns: Intelligence Index first, then others
    priority_metrics = [
        "ArtificialAnalysisIntelligence Index",
        "MedianTokens/s",
        "LatencyFirst Answer Chunk (s)",
        "InputPriceUSD/1M Tokens",
        "OutputPriceUSD/1M Tokens",
        "MMLU-Pro(Reasoning &Knowledge)",
        "LiveCodeBench(Coding)",
        "GPQA Diamond(ScientificReasoning)",
        "Humanity's LastExam(Reasoning & Knowledge)",
        "Terminal-BenchHard (AgenticCoding & Terminal Use)",
        "\ud835\udf0f\u00b2-BenchTelecom(Agentic Tool Use)"
    ]
    
    sorted_metrics = [m for m in priority_metrics if m in metric_cols]
    sorted_metrics += [m for m in metric_cols if m not in priority_metrics]
    
    final_cols = base_cols + sorted_metrics
    
    # Create the report dataframe
    report_df = df[final_cols].copy()
    
    # Rename columns for better readability
    rename_map = {
        "id": "OpenRouter ID",
        "name": "Model Name",
        "context_length": "Context",
        "match_status": "Match",
        "ArtificialAnalysisIntelligence Index": "Intelligence",
        "MedianTokens/s": "TPS",
        "LatencyFirst Answer Chunk (s)": "TTFT (s)",
        "InputPriceUSD/1M Tokens": "Input Price ($/1M)",
        "OutputPriceUSD/1M Tokens": "Output Price ($/1M)",
        "MMLU-Pro(Reasoning &Knowledge)": "MMLU-Pro",
        "LiveCodeBench(Coding)": "LiveCodeBench",
        "GPQA Diamond(ScientificReasoning)": "GPQA Diamond",
        "Humanity's LastExam(Reasoning & Knowledge)": "LastExam",
        "Terminal-BenchHard (AgenticCoding & Terminal Use)": "Terminal-BenchHard",
        "\ud835\udf0f\u00b2-BenchTelecom(Agentic Tool Use)": "Tau-BenchTelecom"
    }
    report_df.rename(columns=rename_map, inplace=True)
    
    # 1. Generate Markdown Report
    markdown_table = report_df.to_markdown(index=False)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("# Free Models Performance Report\n\n")
        f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**[View Sortable HTML Report]({HTML_REPORT_FILE.name})**\n\n")
        f.write(markdown_table)
        f.write("\n\n*Note: Metrics are dynamically discovered from Artificial Analysis leaderboard.*\n")

    # 2. Generate Sortable HTML Report
    html_table = report_df.to_html(index=False, classes="display", table_id="reportTable")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Free Models Performance Report</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
        <script type="text/javascript" charset="utf8" src="https://code.jquery.com/jquery-3.7.0.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
        <style>
            body {{ font-family: sans-serif; margin: 20px; }}
            h1 {{ color: #333; }}
            .dataTables_wrapper {{ margin-top: 20px; }}
            table.dataTable thead th {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h1>Free Models Performance Report</h1>
        <p>Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        {html_table}
        <script>
            $(document).ready(function() {{
                $('#reportTable').DataTable({{
                    "pageLength": 50,
                    "order": [[4, "desc"]] // Sort by Intelligence by default
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    with open(HTML_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Reports generated: {REPORT_FILE} and {HTML_REPORT_FILE}")

def main():
    free_models = fetch_openrouter_free_models()
    aa_data = scrape_artificial_analysis()
    matched_results = match_models(free_models, aa_data)
    generate_report(matched_results)

if __name__ == "__main__":
    main()
