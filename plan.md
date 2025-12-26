## Plan: Enrich OpenRouter Free Models with Performance Data

Build a Python tool that fetches OpenRouter “free” models and enriches them with Artificial Analysis overall metrics plus per-category/benchmark scores, outputting a Markdown comparison table. Category columns are discovered dynamically (to survive column drift), and matching is conservative: aliases are authoritative, and anything uncertain stays unmatched.

### Acknowledgments
- Use `uv` for Python package/dependency management.
- Matching policy: **aliases file is authoritative**; if no safe match, **leave unmatched** (but include in report with empty metrics).

### Steps
1. **Project scaffold + config**: Set up `enrich_models.py` with `httpx` for API calls and `Playwright` for scraping JS-rendered content from [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models).
2. **Fetch and filter OpenRouter free models**: Call OpenRouter `/api/v1/models`, filter to models where all `pricing` fields are `"0"`. Cache the results.
3. **Extract Artificial Analysis metrics with dynamic category discovery**: Scrape the leaderboard using Playwright to obtain base metrics (Intelligence Index, TPS, TTFT) plus all available category/benchmark scores (e.g., SWE-Bench, Tau Bench). Discover category columns dynamically.
4. **Match models (conservative, aliases-authoritative)**: Use a `model_aliases.json` file as the primary source of truth. Supplement with high-confidence fuzzy matching. If ambiguous, leave unmatched.
5. **Generate the Markdown report**: Produce a table in `free_models_report.md` with stable base columns followed by dynamically discovered category columns. Include all free models, even if unmatched (with empty metric cells).

### Further Considerations
1. **Scraping Robustness**: Playwright is used to handle dynamic content and JS rendering on Artificial Analysis.
2. **Matching Accuracy**: Conservative matching with a high threshold for fuzzy matching, backed by an authoritative aliases file.
3. **Caching**: Implement local caching for both OpenRouter and Artificial Analysis data to avoid repeated network calls and respect rate limits.

### New Files To Add
- `model_aliases.json`: Manual mapping file (OpenRouter ID -> Artificial Analysis name).
- `cache/`: Directory for storing cached API responses and scraped data.

