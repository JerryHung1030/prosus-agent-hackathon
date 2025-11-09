"""Headless scraping entrypoint for the housing hunters."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import httpx
from dotenv import load_dotenv

from history import History
from hunters.hunter import Hunter, Prey
from hunters.pararius import Pararius
from utils.image_downloader import ImageDownloader


ALL_HUNTERS: List[Hunter] = [Pararius()]


@dataclass
class Config:
    min_price: Optional[int]
    max_price: Optional[int]
    scraper_version: str
    sleep_seconds: int
    backend_api_url: str
    max_concurrency: int


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
    max_concurrency = parse_int("MAX_CONCURRENCY", os.getenv("MAX_CONCURRENCY")) or 5
    if max_concurrency < 1:
        raise ValueError("MAX_CONCURRENCY must be >= 1")

    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("MINIMUM_PRICE cannot be greater than MAXIMUM_PRICE")

    return Config(
        min_price=min_price,
        max_price=max_price,
        scraper_version=scraper_version,
        sleep_seconds=sleep_seconds,
        backend_api_url=backend_api_url,
        max_concurrency=max_concurrency,
    )


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def publish_listing(listing: dict, config: Config, client: httpx.AsyncClient) -> bool:
    listing_id = listing.get("id") or listing.get("url")
    endpoint = f"{config.backend_api_url.rstrip('/')}/ingest-listings"
    logging.info("Publishing listing %s to %s", listing_id, endpoint)
    try:
        response = await client.post(endpoint, json=[listing])
    except httpx.HTTPError:
        logging.exception("Failed to publish listing %s", listing_id)
        return False

    try:
        payload = response.json()
    except ValueError:
        payload = None

    inserted = payload.get("inserted") if isinstance(payload, dict) else None
    total = payload.get("total") if isinstance(payload, dict) else None
    logging.info(
        "Published listing %s successfully (status=%s)",
        listing_id,
        response.status_code,
    )
    return True


async def process_prey(
    prey: Prey,
    hunter: Hunter,
    config: Config,
    history: History,
    known_urls: set[str],
    known_urls_lock: asyncio.Lock,
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    image_downloader: ImageDownloader,
) -> None:
    async with semaphore:
        try:
            listing = await asyncio.to_thread(hunter.build_json, prey)
        except NotImplementedError:
            logging.info("Hunter %s does not support detail extraction yet", hunter.name)
            return
        except Exception:  # pragma: no cover - site parsing variability
            logging.exception("Failed to build listing JSON for %s", prey.link)
            return

        price_amount = extract_price_amount(listing)
        if price_amount is None:
            logging.warning("Skipping %s due to missing price", prey.link)
            return

        if config.min_price is not None and price_amount < config.min_price:
            logging.info("Skipping %s because %s < MINIMUM_PRICE", prey.link, price_amount)
            return
        if config.max_price is not None and price_amount > config.max_price:
            logging.info("Skipping %s because %s > MAXIMUM_PRICE", prey.link, price_amount)
            return

        listing.setdefault("url", prey.link)
        listing.setdefault("title", prey.name)
        listing.setdefault("agency", {"name": prey.agency or "Unknown"})

        listing["first_seen"] = datetime.now().astimezone().isoformat()
        metadata = listing.setdefault("scrape_meta", {})
        metadata.setdefault("source", hunter.name.lower())
        metadata["scraper_version"] = config.scraper_version

        # Download and cache thumbnail image
        listing_id = listing.get("id")
        html_content = listing.pop("_html_content", None)
        
        if listing_id and html_content:
            try:
                thumbnail_path = await image_downloader.download_from_og_meta(
                    listing_id,
                    html_content,
                )
                if thumbnail_path:
                    listing["thumbnail_path"] = thumbnail_path
                    logging.info("Successfully downloaded thumbnail for listing %s", listing_id)
            except Exception:
                logging.exception("Failed to download thumbnail for listing %s", listing_id)

        if await publish_listing(listing, config, client):
            await asyncio.to_thread(history.add, prey.link)
            async with known_urls_lock:
                known_urls.add(prey.link)
        else:
            logging.warning(
                "Will retry %s later because publishing failed",
                listing.get("id", prey.link),
            )


async def run_once(config: Config, history: History) -> None:
    known_urls = history.get_all()
    known_urls_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(config.max_concurrency)
    
    # Initialize image downloader
    # Check if running in Docker (images mounted at /app/images) or locally (../images from src/)
    if os.path.exists("/app/images"):
        images_path = "/app/images"
    else:
        images_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "images")
    image_downloader = ImageDownloader(base_path=images_path, quality=85)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for hunter in ALL_HUNTERS:
            try:
                preys = await asyncio.to_thread(hunter.hunt)
            except Exception:  # pragma: no cover - network variability
                logging.exception("Hunter %s failed while hunting", hunter.name)
                continue

            new_preys = [prey for prey in preys if prey.link not in known_urls]
            if not new_preys:
                logging.info("Hunter %s produced no new listings", hunter.name)
                continue

            logging.info("Hunter %s produced %s new listings", hunter.name, len(new_preys))

            tasks = [
                process_prey(
                    prey,
                    hunter,
                    config,
                    history,
                    known_urls,
                    known_urls_lock,
                    semaphore,
                    client,
                    image_downloader,
                )
                for prey in new_preys
            ]
            if tasks:
                await asyncio.gather(*tasks)


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


async def scrape_loop(config: Config, history: History, run_once_only: bool) -> None:
    try:
        while True:
            await run_once(config, history)
            if run_once_only:
                break
            logging.info("Sleeping for %s seconds", config.sleep_seconds)
            await asyncio.sleep(config.sleep_seconds)
    finally:
        for hunter in ALL_HUNTERS:
            await asyncio.to_thread(hunter.close)


async def async_main(args: argparse.Namespace) -> None:
    setup_logging()
    try:
        config = load_config()
    except ValueError as exc:
        logging.error("Configuration error: %s", exc)
        sys.exit(2)

    history = History("history.txt")
    await scrape_loop(config, history, args.once)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the housing scraper headlessly.")
    parser.add_argument("--once", action="store_true", help="Run hunters once and exit.")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
