"""Pararius hunter implementation using static HTTP requests."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .hunter import Hunter, Prey


class Pararius(Hunter):
    UNLIMITED_DURATION_MONTHS = 1_000_000

    BASE_URL = "https://www.pararius.com"
    LIST_URL = f"{BASE_URL}/apartments/nederland"
    MAX_PAGES = 10000
    TIMEOUT = 30

    def __init__(self) -> None:
        super().__init__(name="Pararius")

    def hunt(self) -> List[Prey]:
        listings: List[Prey] = []
        seen_links: set[str] = set()
        for page in range(1, self.MAX_PAGES + 1):
            page_url = self._page_url(page)
            logging.debug("Fetching Pararius page %s", page_url)
            response = self.session.get(page_url, timeout=self.TIMEOUT)
            if response.status_code != 200:
                logging.warning("Pararius hunt failed with status %s on %s", response.status_code, page_url)
                break

            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select("li.search-list__item")
            if not cards:
                logging.info("Pararius hunt reached page %s with no listings", page)
                break

            for card in cards:
                anchor = card.select_one("a.listing-search-item__link--title")
                if anchor is None or not anchor.get("href"):
                    continue
                link = urljoin(self.BASE_URL, anchor["href"])
                if link in seen_links:
                    continue

                name = anchor.get_text(strip=True)
                price_text = card.select_one("span.listing-search-item__price") or card.select_one(
                    "div.listing-search-item__price"
                )
                price_amount = self._parse_price(price_text.get_text(strip=True) if price_text else "")

                agency_element = card.select_one("div.listing-search-item__info a")
                agency_name = agency_element.get_text(strip=True) if agency_element else None

                listings.append(Prey(name=name, price=price_amount, link=link, agency=agency_name, source=self.name))
                seen_links.add(link)

        logging.info("Pararius hunt produced %s listings", len(listings))
        return listings

    def build_json(self, prey: Prey) -> Dict[str, Any]:
        logging.debug("Fetching Pararius detail page %s", prey.link)
        response = self.session.get(prey.link, timeout=self.TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        json_ld = self._extract_listing_ld(soup)
        details_map = self._extract_details_map(soup)

        listing_id = self._build_listing_id(prey.link)
        title = json_ld.get("name") if isinstance(json_ld, dict) else None
        if not title:
            heading = soup.select_one("h1.listing-detail-summary__title")
            title = heading.get_text(strip=True) if heading else prey.name

        price_info = self._extract_price_block(json_ld, details_map)
        if price_info.get("amount") is None:
            raise ValueError(f"Missing price information for {prey.link}")

        area_m2 = self._extract_area(json_ld, details_map)
        if area_m2 is None:
            raise ValueError(f"Missing living area for {prey.link}")

        address = self._extract_address(json_ld, soup)
        if not address.get("street") or not address.get("city"):
            raise ValueError(f"Incomplete address data for {prey.link}")

        housing_type = self._extract_housing_type(json_ld, details_map)
        if housing_type is None:
            raise ValueError(f"Missing housing type for {prey.link}")

        agency = self._extract_agency(soup, prey)

        listing: Dict[str, Any] = {
            "id": listing_id,
            "url": prey.link,
            "title": title,
            "price": price_info,
            "area_m2": area_m2,
            "address": address,
            "housing_type": housing_type,
            "agency": agency,
            "scrape_meta": {"source": self.name.lower()},
        }

        furnishing = self._extract_furnishing(soup, details_map)
        if furnishing:
            listing["furnishing"] = furnishing

        deposit = self._parse_price(details_map.get("Deposit", ""))
        if deposit:
            listing["deposit"] = deposit

        contract = self._extract_contract(details_map)
        if contract:
            listing["contract"] = contract

        pets_allowed = self._extract_pets(details_map)
        if pets_allowed is not None:
            listing["pets_allowed"] = pets_allowed

        service_costs = self._parse_price(details_map.get("Service costs", ""))
        if service_costs:
            listing["price"]["service_costs"] = service_costs

        description = self._extract_description(soup)
        if description:
            listing["description"] = description

        return listing

    def _page_url(self, page: int) -> str:
        if page <= 1:
            return self.LIST_URL
        logging.info("Fetching Pararius page %d", page)
        return f"{self.LIST_URL}/page-{page}"

    @staticmethod
    def _parse_price(text: str) -> Optional[int]:
        if not text:
            return None

        match = re.search(r"(\d[\d.,]*)", text)
        if not match:
            return None

        value = match.group(1).replace("\xa0", "").replace(" ", "")

        separators = [(sep, value.rfind(sep)) for sep in (",", ".") if sep in value]
        decimal_sep = None
        if separators:
            sep, idx = max(separators, key=lambda item: item[1])
            digits_after = len(value) - idx - 1
            if 1 <= digits_after <= 2:
                decimal_sep = sep

        if decimal_sep:
            idx = value.rfind(decimal_sep)
            integer_part = re.sub(r"[^0-9]", "", value[:idx])
            fractional_part = re.sub(r"[^0-9]", "", value[idx + 1 :])
            normalized = integer_part or "0"
            if fractional_part:
                normalized = f"{normalized}.{fractional_part}"
        else:
            normalized = re.sub(r"[^0-9]", "", value)
            # if no decimal separator, remove any remaining thousands markers
            normalized = re.sub(r"[^0-9]", "", normalized)

        if not normalized:
            return None

        if not decimal_sep:
            # remove thousands separators from original string by collapsing repeated separators
            normalized = normalized.lstrip("0") or "0"

        try:
            amount = Decimal(normalized)
        except InvalidOperation:
            return None

        integral = amount.to_integral_value(rounding=ROUND_DOWN)
        return int(integral)

    def _extract_listing_ld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        for script in soup.select("script[type='application/ld+json']"):
            if not script.string:
                continue
            try:
                payload = json.loads(script.string)
            except json.JSONDecodeError:
                continue
            for candidate in self._iter_ld_objects(payload):
                types = candidate.get("@type")
                if not types:
                    continue
                normalized = [types] if isinstance(types, str) else list(types)
                if any(t in {"House", "Apartment", "Product"} for t in normalized):
                    return candidate
        return {}

    def _extract_details_map(self, soup: BeautifulSoup) -> Dict[str, str]:
        details: Dict[str, str] = {}
        for container in soup.select("div.listing-features"):
            paired = False

            dd_items = container.select(
                "dd.listing-features__term, dd.listing-features__description"
            )
            idx = 0
            while idx < len(dd_items) - 1:
                term_el = dd_items[idx]
                desc_el = dd_items[idx + 1]
                term_classes = term_el.get("class", [])
                desc_classes = desc_el.get("class", [])
                if "listing-features__term" in term_classes and "listing-features__description" in desc_classes:
                    key = term_el.get_text(strip=True)
                    value = desc_el.get_text(separator=" ", strip=True)
                    if key and value:
                        details[key] = value
                        paired = True
                    idx += 2
                    continue
                idx += 1

            if paired:
                continue

            terms = container.select("dt.listing-features__term")
            descriptions = container.select("dd.listing-features__description")
            for term, description in zip(terms, descriptions):
                key = term.get_text(strip=True)
                value = description.get_text(separator=" ", strip=True)
                if key:
                    details[key] = value
        return details

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        # Locate the description container
        container = soup.select_one("wc-listing-detail-description")
        if container is None:
            container = soup.select_one("div.listing-detail-description")
        if container is None:
            return None

        # Extract plain text with spaces instead of line breaks
        text = container.get_text(separator=" ", strip=True)
        if not text:
            return None

        # Remove trailing "More" / "Less" buttons or similar UI text
        text = re.sub(r"\b(More|Less)\b$", "", text.strip(), flags=re.IGNORECASE)

        # Collapse multiple spaces into a single space
        cleaned = re.sub(r"\s+", " ", text).strip()

        return cleaned or None

    def _extract_price_block(self, json_ld: Dict[str, Any], details: Dict[str, str]) -> Dict[str, Any]:
        offers = json_ld.get("offers") if isinstance(json_ld, dict) else None
        amount = None
        if isinstance(offers, dict):
            amount = self._parse_price(str(offers.get("price", "")))
        if amount is None:
            amount = self._parse_price(details.get("Rent", ""))
        return {"amount": amount, "frequency": "month"}

    def _extract_area(self, json_ld: Dict[str, Any], details: Dict[str, str]) -> Optional[int]:
        floor_size = json_ld.get("floorSize") if isinstance(json_ld, dict) else None
        if isinstance(floor_size, dict):
            area = floor_size.get("value")
            if isinstance(area, (int, float)):
                return int(area)
            if isinstance(area, str):
                parsed = self._parse_price(area)
                if parsed is not None:
                    return parsed
        return self._parse_price(details.get("Living area", ""))

    def _extract_address(self, json_ld: Dict[str, Any], soup: BeautifulSoup) -> Dict[str, Any]:
        address_ld = json_ld.get("address") if isinstance(json_ld, dict) else None
        result: Dict[str, Any] = {}
        if isinstance(address_ld, dict):
            result["street"] = address_ld.get("streetAddress")
            result["city"] = address_ld.get("addressLocality")
            if address_ld.get("addressRegion"):
                result["neighborhood"] = address_ld.get("addressRegion")
            if address_ld.get("postalCode"):
                result["postal_code"] = address_ld.get("postalCode")
        if not result.get("street"):
            street = soup.select_one("span.listing-detail-summary__address")
            if street:
                result["street"] = street.get_text(strip=True)
        if not result.get("city"):
            breadcrumb_city = soup.select("wc-breadcrumbs li a")
            if breadcrumb_city:
                result["city"] = breadcrumb_city[-1].get_text(strip=True)
        return result

    def _extract_housing_type(self, json_ld: Dict[str, Any], details: Dict[str, str]) -> Optional[str]:
        raw_types: Iterable[str] = []
        types = json_ld.get("@type") if isinstance(json_ld, dict) else None
        if isinstance(types, str):
            raw_types = [types]
        elif isinstance(types, list):
            raw_types = types

        for raw in raw_types:
            if raw != "Product":
                return raw.upper()

        property_type = details.get("Property type")
        if property_type:
            return property_type.upper()
        return None

    def _extract_agency(self, soup: BeautifulSoup, prey: Prey) -> Dict[str, Any]:
        agency_name = None
        agency_link = soup.select_one("a.agent-summary__title-link")
        if agency_link:
            agency_name = agency_link.get_text(strip=True)
        if not agency_name:
            agency_name = prey.agency or "Unknown"

        email_link = soup.select_one("a[href^='mailto:']")
        email = email_link["href"].split(":", 1)[1] if email_link else None

        contact_btn = soup.select_one("a.listing-reaction-button--contact-agent")
        if contact_btn is None:
            contact_btn = soup.select_one("a.button--orange[href*='/contact/estate-agent']")
        contact_url = None
        if contact_btn and contact_btn.get("href"):
            contact_url = urljoin(self.BASE_URL, contact_btn["href"])
        logging.info("contact_url=%s", contact_url)
        agency: Dict[str, Any] = {"name": agency_name}
        if email:
            agency["email"] = email
        if contact_url:
            agency["contact_url"] = contact_url
        return agency

    def _map_furnishes(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        normalized = value.strip().lower()
        mapping = {
            "furnished": "FURNISHED",
            "fully furnished": "FURNISHED",
            "unfurnished": "UNFURNISHED",
            "bare": "UNFURNISHED",
            "upholstered": "UPHOLSTERED",
            "partially furnished": "PARTIALLY_FURNISHED",
            "semi-furnished": "PARTIALLY_FURNISHED",
            "upholstered or furnished": "UPHOLSTERED_OR_FURNISHED",
        }
        if normalized in mapping:
            return mapping[normalized]
        if "upholstered" in normalized and "furnished" in normalized:
            return "UPHOLSTERED_OR_FURNISHED"
        return None

    def _extract_furnishing(self, soup: BeautifulSoup, details: Dict[str, str]) -> Optional[str]:
        furnishes = self._map_furnishes(details.get("Interior"))
        if furnishes:
            return furnishes
        for item in soup.select("li.illustrated-features__item--interior"):
            furnishes = self._map_furnishes(item.get_text(strip=True))
            if furnishes:
                return furnishes
        return None

    def _extract_contract(self, details: Dict[str, str]) -> Dict[str, Any]:
        contract: Dict[str, Any] = {}

        available = details.get("Available")
        if available:
            date = self._parse_date(available)
            if date:
                contract["start_date"] = date

        rental_agreement = details.get("Rental agreement") or details.get("Rental period")
        if rental_agreement:
            contract["rental_agreement"] = rental_agreement

        duration_text = details.get("Duration") or ""
        duration_min, duration_max = self._parse_duration_range(duration_text)

        unlimited = False
        if rental_agreement and any(word in rental_agreement.lower() for word in ("unlimited", "indefinite")):
            unlimited = True
        if (duration_text and "unlimited" in duration_text.lower()) or (duration_text and "indefinite" in duration_text.lower()):
            unlimited = True

        if unlimited:
            contract["duration_months"] = 0
            duration_max = self.UNLIMITED_DURATION_MONTHS
            if duration_min is None:
                duration_min = 0
        else:
            primary = duration_min if duration_min is not None else duration_max
            if primary is not None:
                contract["duration_months"] = primary

        if duration_min is None:
            duration_min = 0

        if duration_max is None:
            duration_max = duration_min if duration_min is not None else 0
        elif unlimited and duration_max < duration_min:
            duration_max = max(duration_min, self.UNLIMITED_DURATION_MONTHS)
        elif duration_max < duration_min:
            duration_max = duration_min

        if not unlimited and "duration_months" not in contract:
            contract["duration_months"] = duration_min

        contract["duration_min_months"] = duration_min
        contract["duration_max_months"] = duration_max

        return contract if contract else {}

    def _parse_duration_range(self, text: str) -> tuple[Optional[int], Optional[int]]:
        if not text:
            return (None, None)

        matches = []
        for raw_value, unit in re.findall(r"(\d+(?:[.,]\d+)?)\s*(year|years|yr|yrs|month|months|mo|mos|mth|mths)?", text, flags=re.IGNORECASE):
            value = raw_value.replace(",", ".")
            try:
                number = float(value)
            except ValueError:
                continue
            unit_lower = (unit or "month").lower()
            if "year" in unit_lower or unit_lower.startswith("yr"):
                number *= 12
            matches.append(int(round(number)))

        lower = text.lower()
        min_months = max_months = None

        # Recognize more variants
        if any(k in lower for k in ("minimum", "at least", "from", "min", "min.")):
            if matches:
                min_months = matches[0]
        if any(k in lower for k in ("maximum", "max", "max.", "up to", "no longer than", "until")):
            if matches:
                max_months = matches[-1]

        # Handle "X to Y months"
        range_match = re.search(r"(\d+)\s*(?:to|-|–|—)\s*(\d+)\s*(?:month|months|yr|year|years)", lower)
        if range_match:
            min_months = int(range_match.group(1))
            max_months = int(range_match.group(2))
            if "year" in range_match.group(0):
                min_months *= 12
                max_months *= 12

        if min_months is None and max_months is None and matches:
            if len(matches) == 1:
                min_months = max_months = matches[0]
            elif len(matches) >= 2:
                min_months, max_months = matches[0], matches[1]

        return (min_months, max_months)


    def _extract_pets(self, details: Dict[str, str]) -> Optional[bool]:
        value = details.get("Pets allowed")
        if not value:
            return None
        normalized = value.strip().lower()
        if normalized in {"yes", "allowed"}:
            return True
        if normalized in {"no", "not allowed"}:
            return False
        return None

    def _parse_date(self, value: str) -> Optional[str]:
        patterns = ["%d-%m-%Y", "%d/%m/%Y"]
        for pattern in patterns:
            try:
                dt = datetime.strptime(value.strip(), pattern)
                return dt.date().isoformat()
            except ValueError:
                continue
        return None

    def _build_listing_id(self, url: str) -> str:
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        slug = path_parts[-2] if len(path_parts) >= 2 else path_parts[-1]
        return f"pararius-{slug}" if slug else f"pararius-{abs(hash(url))}"

    def _iter_ld_objects(self, payload: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(payload, dict):
            yield payload
            for value in payload.values():
                yield from self._iter_ld_objects(value)
        elif isinstance(payload, list):
            for item in payload:
                yield from self._iter_ld_objects(item)

