# Netherlands Apartment Hunter

Headless scraper for Dutch housing listings. The current implementation focuses on extracting rich Pararius data and writing discoveries to local JSON files.

## Key Features

- Runs as a CLI loop (no Telegram dependency).
- Deduplicates by listing URL using `history.txt`.
- Stores structured listings in `results.json` with source metadata.
- Pararius hunter follows search pagination and scrapes detail pages for price, address, living area, contract info, and more.

## Requirements

- Python 3.10+
- Recommended: virtual environment (`python -m venv .venv`)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Settings are controlled via environment variables. Create a `.env` file in the project root if you want to override defaults.

| Variable | Description | Default |
| --- | --- | --- |
| `MINIMUM_PRICE` | Skip listings cheaper than this amount (EUR) | unset |
| `MAXIMUM_PRICE` | Skip listings more expensive than this amount (EUR) | unset |
| `SLEEP_SECONDS` | Delay between runs when looping | 240 |
| `SCRAPER_VERSION` | Included in `scrape_meta.scraper_version` | `homepilot-0.2` |

Example `.env`:

```env
MINIMUM_PRICE=800
MAXIMUM_PRICE=2000
SLEEP_SECONDS=300
```

## Running the Scraper

- Single pass (useful for cron jobs):

  ```bash
  python -m src.main --once
  ```

- Continuous loop:

  ```bash
  python -m src.main
  ```

The scraper creates/updates:

- `results.json` – JSON array of structured listings.
- `history.txt` – newline-delimited URLs that have already been processed.

## Current Hunters

- `Pararius` – fully implemented with pagination and detail parsing.
- `Gruno`, `Kamernet`, `Wonen123` – skeleton classes ready for future work.

## Extending

To add a new site:

1. Subclass `Hunter`, implement `hunt()` (returns `Prey` objects) and `build_json()` (returns a dict ready to persist).
2. Add the new hunter to `ALL_HUNTERS` in `src/main.py`.
3. Ensure the detail JSON contains `price.amount`, `area_m2`, and `address` fields so the main loop can filter and store records.

## License

This project is licensed under the terms of the MIT License. See the [LICENSE](LICENSE) file for the full text.
