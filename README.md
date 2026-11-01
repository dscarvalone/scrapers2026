# scrapers2026

A collection of web scrapers.

## Layout

- `scrapers/` — one module per scraper
- `output/` — scraped data (git-ignored)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
python -m scrapers.<scraper_name>
```
