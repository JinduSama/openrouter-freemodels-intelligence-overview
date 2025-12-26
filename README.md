# Find Best or Free Model

This project fetches free models from OpenRouter and enriches them with performance metrics from Artificial Analysis.

## Reports

- **[Markdown Report](output/free_models_report.md)**: A quick overview of free models sorted by Intelligence.
- **[HTML Report](output/free_models_report.html)**: A sortable and searchable table of all free models.

## How it works

1.  **Fetch**: Retrieves the list of free models from the OpenRouter API.
2.  **Scrape**: Scrapes the Artificial Analysis leaderboard for the latest performance metrics.
3.  **Match**: Matches OpenRouter models with Artificial Analysis data using exact and fuzzy matching.
4.  **Report**: Generates Markdown and HTML reports.

## Automation

A GitHub Action runs daily to keep the reports up to date.

## Development

To run the script locally:

```bash
uv sync
uv run playwright install chromium
uv run python -m src.main
```
