"""Headless scraping entrypoint for the housing hunters."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import requests
from dotenv import load_dotenv

from history import History
from hunters.hunter import Hunter
from hunters.pararius import Pararius


ALL_HUNTERS: List[Hunter] = [Pararius()]


@dataclass
class Config:
    min_price: Optional[int]
    max_price: Optional[int]
    scraper_version: str
    sleep_seconds: int
    backend_api_url: str


def parse_int(name: str, value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {value!r}") from exc


def load_config() -> Config:
    load_dotenv()
    min_price = parse_int("MINIMUM_PRICE", os.getenv("MINIMUM_PRICE"))
    max_price = parse_int("MAXIMUM_PRICE", os.getenv("MAXIMUM_PRICE"))
    sleep_seconds = parse_int("SLEEP_SECONDS", os.getenv("SLEEP_SECONDS")) or 0
    scraper_version = os.getenv("SCRAPER_VERSION", "homepilot-0.2")
    backend_api_url = os.getenv("BACKEND_API_URL", "http://localhost:8000")

    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("MINIMUM_PRICE cannot be greater than MAXIMUM_PRICE")

    return Config(
        min_price=min_price,
        max_price=max_price,
        scraper_version=scraper_version,
        sleep_seconds=sleep_seconds,
        backend_api_url=backend_api_url,
    )


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def publish_listing(listing: dict, config: Config) -> bool:
    listing_id = listing.get("id") or listing.get("url")
    endpoint = f"{config.backend_api_url.rstrip('/')}/ingest-listings"
    logging.info("Publishing listing %s to %s", listing_id, endpoint)
    try:
        response = requests.post(endpoint, json=[listing], timeout=30)
    except requests.RequestException:
        logging.exception("Failed to publish listing %s", listing_id)
        return False

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if not response.ok:
        logging.error(
            "Publishing listing %s failed: status=%s body=%s",
            listing_id,
            response.status_code,
            payload,
        )
        return False

    inserted = payload.get("inserted") if isinstance(payload, dict) else None
    total = payload.get("total") if isinstance(payload, dict) else None
    logging.info(
        "Published listing %s successfully (status=%s inserted=%s total=%s)",
        listing_id,
        response.status_code,
        inserted,
        total,
    )
    return True


def run_once(config: Config, history: History) -> None:
    known_urls = history.get_all()

    for hunter in ALL_HUNTERS:
        try:
            preys = hunter.hunt()
        except Exception:  # pragma: no cover - network variability
            logging.exception("Hunter %s failed while hunting", hunter.name)
            continue

        new_preys = [prey for prey in preys if prey.link not in known_urls]
        if not new_preys:
            logging.info("Hunter %s produced no new listings", hunter.name)
            continue

        logging.info("Hunter %s produced %s new listings", hunter.name, len(new_preys))

        for prey in new_preys:
            try:
                listing = hunter.build_json(prey)
            except NotImplementedError:
                logging.info("Hunter %s does not support detail extraction yet", hunter.name)
                continue
            except Exception:  # pragma: no cover - site parsing variability
                logging.exception("Failed to build listing JSON for %s", prey.link)
                continue

            price_amount = extract_price_amount(listing)
            if price_amount is None:
                logging.warning("Skipping %s due to missing price", prey.link)
                continue

            if config.min_price is not None and price_amount < config.min_price:
                logging.info("Skipping %s because %s < MINIMUM_PRICE", prey.link, price_amount)
                continue
            if config.max_price is not None and price_amount > config.max_price:
                logging.info("Skipping %s because %s > MAXIMUM_PRICE", prey.link, price_amount)
                continue

            listing.setdefault("url", prey.link)
            listing.setdefault("title", prey.name)
            listing.setdefault("agency", {"name": prey.agency or "Unknown"})

            listing["first_seen"] = datetime.now().astimezone().isoformat()
            metadata = listing.setdefault("scrape_meta", {})
            metadata.setdefault("source", hunter.name.lower())
            metadata["scraper_version"] = config.scraper_version

            if publish_listing(listing, config):
                history.add(prey.link)
                known_urls.add(prey.link)
            else:
                logging.warning(
                    "Will retry %s later because publishing failed",
                    listing.get("id", prey.link),
                )


def extract_price_amount(listing: dict) -> Optional[int]:
    price_block = listing.get("price")
    if not isinstance(price_block, dict):
        return None
    amount = price_block.get("amount")
    if isinstance(amount, int):
        return amount
    if isinstance(amount, str) and amount.isdigit():
        return int(amount)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the housing scraper headlessly.")
    parser.add_argument("--once", action="store_true", help="Run hunters once and exit.")
    args = parser.parse_args()

    setup_logging()
    try:
        config = load_config()
    except ValueError as exc:
        logging.error("Configuration error: %s", exc)
        sys.exit(2)

    history = History("history.txt")

    try:
        while True:
            run_once(config, history)
            if args.once:
                break
            logging.info("Sleeping for %s seconds", config.sleep_seconds)
            time.sleep(config.sleep_seconds)
    finally:
        for hunter in ALL_HUNTERS:
            hunter.close()


if __name__ == "__main__":
    main()
