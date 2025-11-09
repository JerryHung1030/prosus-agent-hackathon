# api.py
import hashlib
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi import status as http_status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,  # [MODIFIED] Import FileResponse
    JSONResponse,
)
from pydantic import BaseModel, EmailStr, Field

try:
    # Prefer absolute import when package context is available
    from backend.db import get_connection, init_db  # type: ignore
except ImportError:
    # Fallback to relative import when executed directly (e.g., local scripts)
    from .db import get_connection, init_db  # type: ignore

###############################
# Environment / Path Setup    #
###############################
# Load .env early so OPENAI_API_KEY and others are available before agent availability check
load_dotenv()

# Import agent runner from sibling src/ package (path adjustment then import)
SRC_PATH = os.path.join(os.path.dirname(__file__), "..", "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

# Always try to use the real ConversationMemory from src (safe to import without OPENAI_API_KEY)
try:
    from src.memory import ConversationMemory  # type: ignore
except Exception as mem_exc:
    logging.warning(
        "ConversationMemory import failed (%s); using in-process fallback.", mem_exc
    )
    class ConversationMemory:  # type: ignore
        """Minimal in-process fallback memory with the methods expected by the API."""
        def __init__(self):
            self.sessions: Dict[str, Dict[str, Any]] = {}

        def create_session(self):
            sid = hashlib.md5(str(datetime.now(timezone.utc)).encode()).hexdigest()
            self.sessions[sid] = {
                "session_id": sid,
                "messages": [],
                "criteria": {"city": None, "max_price": None, "min_size": None, "commute_target": None},
                "status": "collecting",
                "search_results": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            return sid

        def get_session(self, session_id):
            return self.sessions.get(session_id)

        def add_message(self, session_id, role, content, metadata=None):
            if session_id not in self.sessions:
                return
            self.sessions[session_id]["messages"].append({
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self.sessions[session_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

        def update_status(self, session_id, status):
            if session_id in self.sessions:
                self.sessions[session_id]["status"] = status
                self.sessions[session_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

        def format_conversation_history(self, session_id, limit=None):
            sess = self.sessions.get(session_id)
            if not sess:
                return ""
            msgs = sess["messages"][-limit:] if limit else sess["messages"]
            return "\n".join(f"{m['role'].upper()}: {m['content']}" for m in msgs)

        def get_criteria(self, session_id):
            sess = self.sessions.get(session_id)
            return sess.get("criteria", {}) if sess else {}

        # --- New methods used by the API code ---
        def update_criteria(self, session_id, updates: Dict[str, Any]):
            sess = self.sessions.get(session_id)
            if not sess:
                return
            if "criteria" not in sess or not isinstance(sess["criteria"], dict):
                sess["criteria"] = {}
            sess["criteria"].update(updates)
            sess["updated_at"] = datetime.now(timezone.utc).isoformat()

        def save_search_results(self, session_id, listings: List[Dict[str, Any]]):
            sess = self.sessions.get(session_id)
            if not sess:
                return
            sess["search_results"] = listings
            sess["updated_at"] = datetime.now(timezone.utc).isoformat()

        def is_ready_to_search(self, session_id) -> bool:
            sess = self.sessions.get(session_id)
            if not sess:
                return False
            crit = sess.get("criteria", {}) or {}
            # Consider "ready" if city OR commute_target and at least one numeric constraint is present
            if crit.get("city"):
                return True
            if crit.get("commute_target") and (crit.get("max_price") or crit.get("min_size")):
                return True
            return False

        def list_sessions(self, limit: int = 10):
            # Return most recent sessions
            sessions = sorted(self.sessions.values(), key=lambda s: s.get("updated_at", ""), reverse=True)
            return sessions[:limit]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AGENT_AVAILABLE = False
if OPENAI_API_KEY:
    try:
        logging.info("OPENAI_API_KEY found; enabling agent features")
        from src.main import run_main_crew  # type: ignore
        AGENT_AVAILABLE = True
        logging.info("Agent features enabled")
    except Exception as import_exc:
        logging.warning("Agent import failed (%s); disabling agent features", import_exc)
        def run_main_crew(*args, **kwargs):  # type: ignore
            raise RuntimeError("Agent crew functionality unavailable")
else:
    logging.info("OPENAI_API_KEY not set; agent disabled")
    def run_main_crew(*args, **kwargs):  # type: ignore
        raise RuntimeError("Agent crew functionality unavailable (no OPENAI_API_KEY)")

app = FastAPI(title="Listings API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# (Already loaded .env earlier) -- do not reload here to avoid side-effects
init_db()  # Ensure tables exist on startup

# Load API keys from environment
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


# ---------- Helper: normalize criteria keys ----------
def _normalize_criteria_input(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Accepts whatever the agent / memory returned and normalizes into canonical keys:
    city, max_price, min_size, commute_target and any other pass-through keys.
    Handles:
      - 'expected_criteria', 'expectedCriteria'
      - 'extracted_criteria'
      - 'criteria'
      - nested forms
      - synonym keys like 'budget' -> max_price
    """
    if not raw:
        return {}

    # If it's a wrapper dict like {"expected_criteria": {...}} find inner dict
    if isinstance(raw, dict) and any(k in raw for k in ("expected_criteria", "expectedCriteria", "extracted_criteria", "criteria", "results")):
        for candidate in ("criteria", "expected_criteria", "expectedCriteria", "extracted_criteria", "results"):
            if candidate in raw and isinstance(raw[candidate], dict):
                raw = raw[candidate]
                break

    if not isinstance(raw, dict):
        return {}

    # canonical mapping
    out: Dict[str, Any] = {}
    # low-level canonical keys we care about
    key_map = {
        # synonyms -> canonical
        "city": "city",
        "location": "city",
        "area": "city",
        "max_price": "max_price",
        "price_max": "max_price",
        "budget": "max_price",
        "min_size": "min_size",
        "size_min": "min_size",
        "min_area": "min_size",
        "commute_target": "commute_target",
        "commute": "commute_target",
        "destination": "commute_target",
    }

    # first pass: map known keys
    for k, v in raw.items():
        lk = k.lower()
        if lk in key_map:
            out[key_map[lk]] = v
        else:
            # if already canonical-looking, pass-through
            if lk in ("city", "max_price", "min_size", "commute_target"):
                out[lk] = v
            else:
                # keep other things available too (bedrooms, furnished, petFriendly etc.)
                out[k] = v

    # normalize numeric strings -> ints for known numeric fields if possible
    if "max_price" in out and isinstance(out["max_price"], str):
        try:
            out["max_price"] = int("".join(ch for ch in out["max_price"] if ch.isdigit()))
        except Exception:
            pass
    if "min_size" in out and isinstance(out["min_size"], str):
        try:
            out["min_size"] = int("".join(ch for ch in out["min_size"] if ch.isdigit()))
        except Exception:
            pass

    return out


# ---------- Pydantic models ----------
class Price(BaseModel):
    amount: Optional[int] = None
    frequency: Optional[str] = None
    service_costs: Optional[int] = Field(default=None, alias="service_costs")


class Address(BaseModel):
    street: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None


class Contract(BaseModel):
    start_date: Optional[str] = None  # ISO string
    duration_months: Optional[int] = None


class Agency(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    contact_url: Optional[str] = None


class ScrapeMeta(BaseModel):
    scraper_version: Optional[str] = None


class ListingIn(BaseModel):
    id: str = Field(..., description="external id, e.g., pararius-123456")
    url: str
    title: Optional[str] = None
    price: Optional[Price] = None
    area_m2: Optional[float] = None
    address: Optional[Address] = None
    housing_type: Optional[str] = None
    furnishes: Optional[str] = None
    deposit: Optional[int] = None
    contract: Optional[Contract] = None
    agency: Optional[Agency] = None
    first_seen: Optional[str] = None  # ISO string
    pets_allowed: Optional[bool] = None
    scrape_meta: Optional[ScrapeMeta] = Field(default=None, alias="scrape_meta")
    thumbnail_path: Optional[str] = None


class LLMStartIn(BaseModel):
    status: str = "running"  # Default status is running
    start_time: Optional[str] = (
        None  # May be provided by LLM; otherwise current time is used
    )


class LLMFinishIn(BaseModel):
    job_id: int
    status: str  # Possible values: finished / error
    result: Optional[Dict[str, Any]] = (
        None  # JSON object payload e.g. {"text": "...", "image_path": "..."}
    )
    end_time: Optional[str] = None


# ---------- Agent Housing Search models ----------
class HousingSearchRequest(BaseModel):
    city: Optional[str] = Field(None, description="City name, e.g., Amsterdam")
    max_price: Optional[int] = Field(None, description="Maximum price")
    min_size: Optional[int] = Field(None, description="Minimum size (square meters)")
    commute_target: Optional[str] = Field(
        None, description="Commute destination address"
    )


class HousingApplyRequest(BaseModel):
    user_profile: Dict[str, Any] = Field(..., description="User profile data")
    listing_details: Dict[str, Any] = Field(..., description="Listing details data")


# [NEW] Model for Chat API
class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = ""


# ---------- Async Job models ----------
class JobStatusResponse(BaseModel):
    id: int
    status: Literal["running", "finished", "error"]
    job_type: Optional[str] = None
    session_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


# ---------- Ingest endpoints ----------
async def geocode_address_internal(address: str) -> tuple[float, float] | None:
    """Internal geocoding function with caching."""
    address = address.strip()
    if not address:
        return None

    address_hash = hash_address(address)

    # Check cache first
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT latitude, longitude FROM address_cache WHERE address_hash = ?",
            (address_hash,),
        )
        cached = cur.fetchone()

        if cached:
            return (cached["latitude"], cached["longitude"])

    # Call Google Geocoding API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "address": address,
                    "key": GOOGLE_MAPS_API_KEY,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logging.error("Geocoding API request failed for '%s': %s", address, exc)
        return None

    if data.get("status") != "OK":
        logging.warning(
            "Geocoding failed for address '%s': %s", address, data.get("status")
        )
        return None

    results = data.get("results", [])
    if not results:
        return None

    location = results[0]["geometry"]["location"]
    latitude = location["lat"]
    longitude = location["lng"]

    # Cache the result
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO address_cache (address_hash, address, latitude, longitude, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(address_hash) DO UPDATE SET
                latitude = excluded.latitude,
                longitude = excluded.longitude
            """,
            (address_hash, address, latitude, longitude, now),
        )
        conn.commit()

    return (latitude, longitude)


@app.post("/ingest-listings")
async def ingest_listings(items: List[ListingIn]):
    """
    Batch receive listings and write to SQLite.
    - Geocodes addresses automatically if not already geocoded
    - Fields with value None will be stored as NULL.
    """
    # Log that we received N items
    logging.info("Ingesting %d listings", len(items))
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    with get_connection() as conn:
        cur = conn.cursor()
        for it in items:
            price = it.price or Price()
            addr = it.address or Address()
            contract = it.contract or Contract()
            agency = it.agency or Agency()
            meta = it.scrape_meta or ScrapeMeta()

            # Build address string for geocoding
            latitude = None
            longitude = None
            address_parts = []
            if addr.street:
                address_parts.append(addr.street)
            if addr.postal_code:
                address_parts.append(addr.postal_code)
            if addr.city:
                address_parts.append(addr.city)

            if address_parts:
                full_address = ", ".join(address_parts) + ", Netherlands"
                coords = await geocode_address_internal(full_address)
                if coords:
                    latitude, longitude = coords
                    logging.info(
                        "Geocoded listing %s: %.6f, %.6f", it.id, latitude, longitude
                    )
                else:
                    logging.warning(
                        "Failed to geocode listing %s with address: %s",
                        it.id,
                        full_address,
                    )

            cur.execute(
                """
                INSERT INTO listings (
                    external_id, url, title,
                    price_amount, price_frequency, service_costs,
                    area_m2, street, neighborhood, city, postal_code,
                    housing_type, furnishes, deposit,
                    contract_start_date, contract_duration_months,
                    agency_name, agency_email, agency_contact_url,
                    first_seen, pets_allowed, scraper_version,
                    thumbnail_path, latitude, longitude, raw_json, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(external_id) DO UPDATE SET
                    url = COALESCE(excluded.url, listings.url),
                    title = COALESCE(excluded.title, listings.title),
                    price_amount = COALESCE(excluded.price_amount, listings.price_amount),
                    price_frequency = COALESCE(excluded.price_frequency, listings.price_frequency),
                    service_costs = COALESCE(excluded.service_costs, listings.service_costs),
                    area_m2 = COALESCE(excluded.area_m2, listings.area_m2),
                    street = COALESCE(excluded.street, listings.street),
                    neighborhood = COALESCE(excluded.neighborhood, listings.neighborhood),
                    city = COALESCE(excluded.city, listings.city),
                    postal_code = COALESCE(excluded.postal_code, listings.postal_code),
                    housing_type = COALESCE(excluded.housing_type, listings.housing_type),
                    furnishes = COALESCE(excluded.furnishes, listings.furnishes),
                    deposit = COALESCE(excluded.deposit, listings.deposit),
                    contract_start_date = COALESCE(excluded.contract_start_date, listings.contract_start_date),
                    contract_duration_months = COALESCE(excluded.contract_duration_months, listings.contract_duration_months),
                    agency_name = COALESCE(excluded.agency_name, listings.agency_name),
                    agency_email = COALESCE(excluded.agency_email, listings.agency_email),
                    agency_contact_url = COALESCE(excluded.agency_contact_url, listings.agency_contact_url),
                    first_seen = COALESCE(listings.first_seen, excluded.first_seen),
                    pets_allowed = COALESCE(excluded.pets_allowed, listings.pets_allowed),
                    scraper_version = COALESCE(excluded.scraper_version, listings.scraper_version),
                    thumbnail_path = COALESCE(excluded.thumbnail_path, listings.thumbnail_path),
                    latitude = COALESCE(excluded.latitude, listings.latitude),
                    longitude = COALESCE(excluded.longitude, listings.longitude),
                    raw_json = COALESCE(excluded.raw_json, listings.raw_json),
                    updated_at = excluded.updated_at
            """,
                (
                    it.id,
                    it.url,
                    it.title,
                    price.amount,
                    price.frequency,
                    price.service_costs,
                    it.area_m2,
                    addr.street,
                    addr.neighborhood,
                    addr.city,
                    addr.postal_code,
                    it.housing_type,
                    it.furnishes,
                    it.deposit,
                    contract.start_date,
                    contract.duration_months,
                    agency.name,
                    agency.email,
                    agency.contact_url,
                    it.first_seen,
                    (
                        1
                        if it.pets_allowed
                        else 0 if it.pets_allowed is not None else None
                    ),
                    meta.scraper_version,
                    it.thumbnail_path,
                    latitude,
                    longitude,
                    json.dumps(it.model_dump(by_alias=True, exclude_none=True)),
                    now,
                    now,
                ),
            )
            inserted += 1

        conn.commit()

    return {"inserted": inserted, "total": len(items)}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points on Earth using haversine formula.
    Returns km."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@app.get("/listings")
def list_listings(
    id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    city: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: Optional[float] = Query(None, alias="radius_km"),
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_area: Optional[int] = None,
    max_area: Optional[int] = None,
    pets_allowed: Optional[bool] = None,
    since: Optional[str] = None,
    q: Optional[str] = None,
    order_by: Literal[
        "first_seen",
        "price_amount",
        "area_m2",
        "updated_at",
        "created_at",
        "id",
        "distance",
    ] = "first_seen",
    order_dir: Literal["asc", "desc"] = "desc",
    include_raw: bool = False,
    fetch_all: bool = Query(False, alias="all"),
):
    """
    List listings with optional filtering by:
    - id: if provided, returns only that specific listing (by id or external_id)
    - city: fuzzy match on city name
    - lat/lng/radius_km: geo-based filtering (all 3 required together)
    - price, area, pets, etc.

    If lat/lng/radius_km are provided, results are sorted by distance and include distance_km field.
    """
    offset = max(0, offset)
    limit = max(1, min(limit, 200))

    cols = [
        "id",
        "external_id",
        "url",
        "title",
        "price_amount",
        "price_frequency",
        "service_costs",
        "area_m2",
        "street",
        "neighborhood",
        "city",
        "postal_code",
        "housing_type",
        "furnishes",
        "deposit",
        "contract_start_date",
        "contract_duration_months",
        "agency_name",
        "agency_email",
        "agency_contact_url",
        "first_seen",
        "pets_allowed",
        "scraper_version",
        "thumbnail_path",
        "latitude",
        "longitude",
        "created_at",
        "updated_at",
        "application_status",  # [MODIFIED] Include new status fields
        "application_screenshot_path",  # [MODIFIED] Include new status fields
    ]
    if include_raw:
        cols.append("raw_json")

    with get_connection() as conn:
        cur = conn.cursor()

        # If id is provided, directly query that single listing
        if id:
            cur.execute(
                f"SELECT {', '.join(cols)} FROM listings WHERE id = ? OR external_id = ? LIMIT 1",
                (id, id),
            )
            row = cur.fetchone()
            return {
                "total": 1 if row else 0,
                "limit": 1,
                "offset": 0,
                "items": [dict(row)] if row else [],
            }

        where = []
        params: List[object] = []

        use_geo_filter = lat is not None and lng is not None and radius is not None

        if use_geo_filter:
            # Narrow Optional types since we checked use_geo_filter above
            lat_f = float(lat)  # type: ignore[arg-type]
            lng_f = float(lng)  # type: ignore[arg-type]
            rad_f = float(radius)  # type: ignore[arg-type]

            # Filter by lat/lng with bounding box for efficiency (1 deg ~ 111km)
            # Guard against negative radius values
            effective_radius = rad_f if rad_f > 0 else 0.0
            lat_delta = effective_radius / 111.0
            # Avoid divide-by-zero issues for longitude degrees at poles
            cos_lat = math.cos(math.radians(lat_f))
            lng_delta = (
                effective_radius / (111.0 * cos_lat) if effective_radius > 0 else 0.0
            )

            where.append("latitude IS NOT NULL")
            where.append("longitude IS NOT NULL")
            where.append("latitude BETWEEN ? AND ?")
            params.extend([lat_f - lat_delta, lat_f + lat_delta])
            where.append("longitude BETWEEN ? AND ?")
            params.extend([lng_f - lng_delta, lng_f + lng_delta])

        if city:
            where.append("LOWER(city) LIKE ?")
            params.append(f"%{city.lower()}%")

        if min_price is not None:
            where.append("price_amount >= ?")
            params.append(min_price)

        if max_price is not None:
            where.append("price_amount <= ?")
            params.append(max_price)

        if min_area is not None:
            where.append("area_m2 >= ?")
            params.append(min_area)

        if max_area is not None:
            where.append("area_m2 <= ?")
            params.append(max_area)

        if pets_allowed is not None:
            where.append("pets_allowed = ?")
            params.append(1 if pets_allowed else 0)

        if since:
            where.append("first_seen >= ?")
            params.append(since)

        if q:
            where.append(
                "(title LIKE ? OR street LIKE ? OR neighborhood LIKE ? OR city LIKE ?)"
            )
            like = f"%{q}%"
            params.extend([like, like, like, like])

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # Fetch all matching rows
        cur.execute(
            f"""
            SELECT {", ".join(cols)}
            FROM listings
            {where_sql}
            """,
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]

        # If geo filtering, compute exact distances and filter by radius
        if use_geo_filter:
            # Use narrowed float vars from earlier block
            lat_f = float(lat)  # type: ignore[arg-type]
            lng_f = float(lng)  # type: ignore[arg-type]
            rad_f = float(radius)  # type: ignore[arg-type]
            items_with_distance = []
            for row in rows:
                if row["latitude"] is not None and row["longitude"] is not None:
                    dist = haversine(lat_f, lng_f, row["latitude"], row["longitude"])
                    if dist <= rad_f:
                        row["distance_km"] = round(dist, 2)
                        row["location"] = {
                            "lat": row["latitude"],
                            "lng": row["longitude"],
                        }
                        items_with_distance.append(row)

            # Sort by distance
            items_with_distance.sort(key=lambda x: x["distance_km"])
            items = items_with_distance
            total = len(items)
        else:
            items = rows
            total = len(items)

            # Apply sorting if not geo-based
            if order_by != "distance":
                reverse = order_dir == "desc"
                if order_by in items[0] if items else {}:
                    items.sort(key=lambda x: x.get(order_by) or "", reverse=reverse)

        # Apply pagination
        if not fetch_all:
            items = items[offset : offset + limit]
        elif offset:
            items = items[offset:]

    return {
        "total": total,
        "limit": len(items) if fetch_all else limit,
        "offset": offset,
        "items": items,
    }


@app.get("/listing/{listing_id}")
def get_listing(listing_id: str):
    """Return a single listing by its internal or external id."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM listings WHERE external_id = ? OR id = ? LIMIT 1",
            (listing_id, listing_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Listing not found")

    data = dict(row)
    raw_json = data.get("raw_json")
    if raw_json:
        try:
            data["raw_json"] = json.loads(raw_json)
        except json.JSONDecodeError:
            logging.warning("Failed to decode raw_json for listing %s", listing_id)

    return data


# ---------- LLM Job endpoints ----------
@app.post("/llm/start")
def llm_start(data: LLMStartIn):
    """Start a new LLM job"""
    start_time = data.start_time or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO llm_jobs (status, start_time) VALUES (?, ?)",
            (data.status, start_time),
        )
        conn.commit()
        job_id = cur.lastrowid
    return {"job_id": job_id, "status": data.status, "start_time": start_time}


@app.post("/llm/finish")
def llm_finish(data: LLMFinishIn):
    """Update specified LLM job result"""
    end_time = data.end_time or datetime.now(timezone.utc).isoformat()
    result_json = json.dumps(data.result) if data.result is not None else None
    with get_connection() as conn:
        conn.execute(
            "UPDATE llm_jobs SET status=?, result=?, end_time=? WHERE id=?",
            (data.status, result_json, end_time, data.job_id),
        )
        conn.commit()
    return {"job_id": data.job_id, "status": data.status, "end_time": end_time}


@app.get("/llm/status")
def llm_status(limit: int = 10):
    """Query recent job status"""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, status, start_time, result, end_time FROM llm_jobs ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]

    for r in rows:
        if r["result"] is not None:
            r["result"] = json.loads(r["result"])
    return {"count": len(rows), "items": rows}


# ---------- Lightweight async job queue helpers ----------
def _create_job(session_id: Optional[str], job_type: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO llm_jobs (session_id, job_type, status, start_time) VALUES (?, ?, ?, ?)",
            (session_id, job_type, "running", now),
        )
        conn.commit()
        job_id = cur.lastrowid
        if job_id is None:
            raise RuntimeError("Failed to create job id")
        return job_id


def _complete_job(
    job_id: int,
    status: Literal["finished", "error"],
    result: Optional[Dict[str, Any]] = None,
):
    end_time = datetime.now(timezone.utc).isoformat()
    result_json = json.dumps(result) if result is not None else None
    with get_connection() as conn:
        conn.execute(
            "UPDATE llm_jobs SET status=?, result=?, end_time=? WHERE id=?",
            (status, result_json, end_time, job_id),
        )
        conn.commit()


def _parse_agent_result(result: Any) -> Dict[str, Any]:
    """Best-effort parse of Agent result into a dict with optional 'listings' and normalized 'criteria'."""
    # --- existing extraction logic ---
    raw_text = None
    if hasattr(result, "json_dict") and getattr(result, "json_dict"):
        try:
            parsed = dict(getattr(result, "json_dict"))
        except Exception:
            parsed = None
        if parsed:
            # Normalize criteria keys if present
            if isinstance(parsed, dict):
                # if parsed contains expected_criteria/extracted_criteria/criteria, normalize into parsed['criteria']
                for candidate in ("expected_criteria", "expectedCriteria", "extracted_criteria", "criteria"):
                    if candidate in parsed and isinstance(parsed[candidate], dict):
                        parsed["criteria"] = _normalize_criteria_input(parsed[candidate])
                        break
            return parsed

    if hasattr(result, "raw"):
        try:
            raw_text = str(getattr(result, "raw"))
        except Exception:
            raw_text = str(result)
    else:
        raw_text = str(result)

    try:
        import re

        match = re.search(r"(\[.*\]|\{.*\})", raw_text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(1))
        else:
            parsed = json.loads(raw_text)
    except Exception:
        return {"raw": raw_text}

    # Normalize listings / results / criteria
    out: Dict[str, Any] = {}
    if isinstance(parsed, dict):
        # Normalize results/listings
        if "listings" in parsed:
            out.update(parsed)
        elif "results" in parsed:
            out.update(parsed)
            out["listings"] = parsed.get("results", [])
        else:
            out.update(parsed)

        # Normalize criteria-like keys into canonical 'criteria'
        for candidate in ("expected_criteria", "expectedCriteria", "extracted_criteria", "criteria"):
            if candidate in parsed:
                out["criteria"] = _normalize_criteria_input(parsed[candidate])
                break

    elif isinstance(parsed, list):
        out["listings"] = parsed
    else:
        out["raw"] = raw_text

    return out


def _run_search_task(job_id: int, session_id: Optional[str], criteria: Dict[str, Any]):
    """Background worker: run housing_search and persist results to llm_jobs (and memory)."""
    try:
        logging.info(
            f"[BG] Starting housing_search job_id={job_id} session_id={session_id} criteria={criteria}"
        )
        result = run_main_crew(
            "housing_search", {"criteria": criteria}, streamlit_callback=None
        )
        parsed = _parse_agent_result(result)
        listings = parsed.get("listings", [])

        # Persist to conversation memory if session_id provided
        try:
            if session_id:
                mem = ConversationMemory()
                mem.save_search_results(session_id, listings)
                mem.update_status(session_id, "AWAITING_APPLY_DECISION")
        except Exception as mem_exc:
            logging.warning(f"[BG] Failed to update conversation memory: {mem_exc}")

        _complete_job(job_id, "finished", {"listings": listings})
        logging.info(
            f"[BG] housing_search completed job_id={job_id} with {len(listings)} listings"
        )
    except Exception as e:
        logging.exception(f"[BG] housing_search error job_id={job_id}: {e}")
        _complete_job(job_id, "error", {"error": str(e)})


def _run_apply_task(job_id: int, payload: Dict[str, Any]):
    """Background worker: run housing_apply and persist results to llm_jobs and DB."""
    try:
        user_profile = payload.get("user_profile")
        listing_details = payload.get("listing_details") or {}

        crew_inputs = {
            "user_profile": json.dumps(user_profile),
            "listing_details": json.dumps(listing_details),
        }

        logging.info(
            f"[BG] Starting housing_apply job_id={job_id} external_id={listing_details.get('external_id')}"
        )
        result = run_main_crew("housing_apply", crew_inputs, streamlit_callback=None)

        # Extract raw text
        if hasattr(result, "raw") and isinstance(result.raw, str):
            result_text = result.raw
        else:
            result_text = str(result)

        # Try to extract screenshot path from tool result
        screenshot_path = None
        if isinstance(result_text, str) and "Screenshot saved as " in result_text:
            try:
                path_part = (
                    result_text.split("Screenshot saved as ")[-1].strip().rstrip(".")
                )
                # Accept paths like "images/listing-id/application_timestamp.png"
                if path_part and path_part.endswith(".png"):
                    screenshot_path = path_part
                    logging.info(f"[BG] Extracted screenshot path: {screenshot_path}")
            except Exception as extract_exc:
                logging.warning(f"[BG] Failed to extract screenshot path: {extract_exc}")

        # Update listings table if possible
        external_id = listing_details.get("external_id")
        if external_id and screenshot_path:
            try:
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        UPDATE listings
                        SET 
                            application_status = ?,
                            application_screenshot_path = ?,
                            updated_at = ?
                        WHERE external_id = ?
                        """,
                        (
                            "applied",
                            screenshot_path,
                            datetime.now(timezone.utc).isoformat(),
                            external_id,
                        ),
                    )
                    rows_updated = cur.rowcount
                    conn.commit()
                    logging.info(
                        f"[BG] ✅ Updated application_screenshot_path for {external_id} "
                        f"(rows affected: {rows_updated}, path: {screenshot_path})"
                    )
            except Exception as db_exc:
                logging.error(
                    f"[BG] ❌ Failed to update application status in DB for {external_id}: {db_exc}"
                )
        elif external_id and not screenshot_path:
            logging.warning(
                f"[BG] ⚠️ No screenshot path extracted for {external_id}, skipping DB update"
            )
        elif screenshot_path and not external_id:
            logging.warning(
                f"[BG] ⚠️ Have screenshot path but no external_id, cannot update DB"
            )

        _complete_job(
            job_id,
            "finished",
            {"message": result_text, "screenshot_path": screenshot_path},
        )
        logging.info(f"[BG] housing_apply completed job_id={job_id}")
    except Exception as e:
        logging.exception(f"[BG] housing_apply error job_id={job_id}: {e}")
        _complete_job(job_id, "error", {"error": str(e)})


# ---------- Job status endpoint for polling ----------
@app.get("/jobs/status/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, status, job_type, session_id, start_time, end_time, result FROM llm_jobs WHERE id=?",
            (job_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        data = dict(row)
        if data.get("result"):
            try:
                data["result"] = json.loads(data["result"])  # type: ignore[assignment]
            except Exception:
                data["result"] = None
        return data  # FastAPI will coerce to JobStatusResponse


# ---------- Agent Housing endpoints ----------


@app.post("/agent/housing/search")
def agent_housing_search(request: HousingSearchRequest):
    """
    Use AI Agents to search and rank housing listings.

    Features:
    1. Search Agent fetches listings from the database matching criteria.
    2. Ranking Agent computes commute times and ranks the top 5 listings.

    Parameters:
    - city: City name (optional)
    - max_price: Maximum price (optional)
    - min_size: Minimum size (optional)
    - commute_target: Commute destination address (optional)

    Returns:
    - Top 5 ranked listings including match_score and commute_time.
    """
    try:
        # Build search criteria
        criteria = {
            "city": request.city,
            "max_price": request.max_price,
            "min_size": request.min_size,
            "commute_target": request.commute_target or "Amsterdam Central Station",
        }
        crew_inputs = {"criteria": criteria}

        logging.info(f"Starting housing search with criteria: {criteria}")
        result = run_main_crew("housing_search", crew_inputs, streamlit_callback=None)

        # Parse crew result using unified parser
        try:
            parsed_result = _parse_agent_result(result)
            
            # Determine listings
            if isinstance(parsed_result, dict):
                if "results" in parsed_result:
                    listings = parsed_result["results"]
                elif "listings" in parsed_result:
                    listings = parsed_result["listings"]
                else:
                    listings = []
            elif isinstance(parsed_result, list):
                listings = parsed_result
            else:
                listings = []

            # Normalize any criteria the agent returned
            agent_criteria = {}
            if isinstance(parsed_result, dict) and any(k in parsed_result for k in ("criteria", "expected_criteria", "expectedCriteria", "extracted_criteria")):
                # prefer parsed_result['criteria'] if present
                agent_criteria = _normalize_criteria_input(
                    parsed_result.get("criteria") or 
                    parsed_result.get("expected_criteria") or 
                    parsed_result.get("expectedCriteria") or 
                    parsed_result.get("extracted_criteria")
                )

            # The API should always return a 'criteria' key with canonical structure.
            return {
                "success": True,
                "criteria": agent_criteria or criteria,   # return agent-updated criteria if present, else the request criteria
                "count": len(listings),
                "listings": listings,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            logging.error(f"Failed to parse agent result as JSON: {e}")
            raw_output = str(result)
            return {
                "success": False,
                "error": f"Failed to parse agent result: {str(e)}",
                "raw_result": raw_output[:500],
                "hint": "Agent may have returned non-JSON output; please check task configuration.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        logging.error(f"Error in agent_housing_search: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.post("/agent/housing/apply")
def agent_housing_apply(
    request: HousingApplyRequest, background_tasks: BackgroundTasks
):
    """
    Use AI Agent to automatically apply for a housing listing.

    Features:
    1. Apply Agent generates a personalized motivation letter.
    2. Automatically fills and submits the application form.
    3. Captures a screenshot as application proof.
    4. [MODIFIED] Stores application status and screenshot path in the database.

    Returns:
    - Application result and screenshot path.
    """
    try:
        # Queue background application task
        payload = {
            "user_profile": request.user_profile,
            "listing_details": request.listing_details,
        }
        job_id = _create_job(session_id=None, job_type="apply")
        background_tasks.add_task(_run_apply_task, job_id, payload)

        started_msg = "Application process started in background."
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={
                "success": True,
                "status": "APPLY_STARTED",
                "job_id": job_id,
                "response": started_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        logging.error(f"Error queueing housing_apply: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/housing/chat")
def agent_housing_chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Conversational housing search (Flow Steps 1-7)

    Features:
    1. Natural conversation with the user.
    2. Incrementally collects search criteria (city, max_price, min_size, commute_target).
    3. Stores conversation history.
    4. Automatically triggers search when criteria are complete (Flow Steps 4-6).
    5. [MODIFIED] After search completes, asks whether to apply (Flow Step 7).
    """
    try:
        # Initialize memory
        memory = ConversationMemory()

        # If agent features are disabled (missing key or import failure), provide a graceful stub response
        if not AGENT_AVAILABLE:
            session_id = request.session_id or memory.create_session()
            if request.message:
                memory.add_message(session_id, "user", request.message)
            agent_reply = (
                "Conversational agent unavailable: missing or invalid configuration (e.g. OPENAI_API_KEY)."
            )
            memory.add_message(session_id, "assistant", agent_reply)
            return JSONResponse(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "session_id": session_id,
                    "error": agent_reply,
                    "criteria": memory.get_criteria(session_id),
                    "is_complete": False,
                    "status": "agent_unavailable",
                    "agent_available": False,
                    "listings": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        session_id = request.session_id
        message = request.message

        # If no session_id provided, create a new session
        if not session_id:
            session_id = memory.create_session()
            logging.info(f"✨ Created new conversation session: {session_id}")
        else:
            logging.info(f"📖 Continuing existing conversation session: {session_id}")

        # Retrieve existing session
        session = memory.get_session(session_id)
        if not session:
            logging.error(f"❌ Session {session_id} not found in memory")
            return {
                "success": False,
                "error": f"Session {session_id} not found",
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Persist user's message (log errors if memory fails)
        try:
            memory.add_message(session_id, "user", message)
            logging.debug(f"💬 Added user message to session {session_id}: {message[:100]}")
        except Exception as mem_exc:
            logging.exception(f"❌ Failed to add user message to memory for session {session_id}: {mem_exc}")

        # --- [NEW] Handle post-search flow (Flow Step 7) ---
        if session["status"] == "AWAITING_APPLY_DECISION":
            positive_responses = ["yes", "好", "要", "請", "apply", "y", "ok"]

            if any(kw in message.lower() for kw in positive_responses):
                memory.update_status(session_id, "APPLY_APPROVED")
                agent_response = "Great! I'm ready. Click 'Apply' on any listing you're interested in and I'll start the application for you."
                memory.add_message(session_id, "assistant", agent_response)

                return {
                    "success": True,
                    "session_id": session_id,
                    "response": agent_response,
                    "criteria": session["criteria"],
                    "is_complete": True,
                    "status": "APPLY_APPROVED",
                    "listings": session.get("search_results"),  # Resend listings
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            else:
                # User declined or provided a different response
                memory.update_status(session_id, "COMPLETED_NO_APPLY")
                agent_response = "No problem. If you change your mind later, you can come back to apply. Have a great day!"
                memory.add_message(session_id, "assistant", agent_response)
                return {
                    "success": True,
                    "session_id": session_id,
                    "response": agent_response,
                    "criteria": session["criteria"],
                    "is_complete": True,
                    "status": "COMPLETED_NO_APPLY",
                    "listings": session.get("search_results"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        # --- End of [NEW] ---

        # Prepare conversation context for the agent
        conversation_history = memory.format_conversation_history(session_id, limit=10)
        current_criteria = memory.get_criteria(session_id)

        crew_inputs = {
            "session_id": session_id,
            "message": message,
            "conversation_history": conversation_history,
            "current_criteria": current_criteria,
        }

        # Execute the conversation agent
        logging.info(f"🤖 Processing conversation for session {session_id}")
        logging.info(f"📋 Current criteria: {current_criteria}")
        logging.info(f"💭 Conversation history (last 10):\n{conversation_history if conversation_history else '(empty)'}")
        # Run the real agent (requires OPENAI_API_KEY)
        result = run_main_crew("conversation", crew_inputs, streamlit_callback=None)

        # result
        try:
            result_str = None
            if hasattr(result, "raw"):
                result_str = result.raw
            else:
                result_str = str(result)

            logging.info(f"Agent result (first 1000 chars): {result_str[:1000]}")

            # Check whether a search was triggered (tool may return TRIGGER_SEARCH)
            import re

            # This logic is from your original code, it's robust
            if hasattr(result, "tasks_output"):
                _ = str(
                    result.tasks_output
                )  # Access for potential side-effects; ignore content

            full_result_str = str(result)
            logging.info(
                f"Full result object (first 1000 chars): {full_result_str[:1000]}"
            )

            # [MODIFIED] Check if agent triggered search (Flow Step 4)
            # The 'trigger_search_tool' returns a specific JSON
            # Note: previously matched 'TRIGGER_SEARCH' but the result isn't used; kept logic minimal.

            # Parse and update criteria captured from agent output
            json_match = re.search(r"\{.*\}", result_str, re.DOTALL)
            parsed_result = {}
            agent_response = result_str  # Fallback
            extracted_criteria = {}
            is_complete = False

            if json_match:
                result_str_json = json_match.group(0)
                try:
                    parsed_result = json.loads(result_str_json)
                    agent_response = parsed_result.get("response", result_str)
                    
                    # Unify extracted criteria from various names using normalizer
                    raw_extracted = (
                        parsed_result.get("extracted_criteria") or 
                        parsed_result.get("expected_criteria") or 
                        parsed_result.get("expectedCriteria") or 
                        parsed_result.get("criteria") or 
                        {}
                    )
                    extracted_criteria = _normalize_criteria_input(raw_extracted or {})
                    is_complete = parsed_result.get("is_complete", False)

                    # Update session criteria with extracted values
                    updates = {k: v for k, v in extracted_criteria.items() if v is not None}
                    if updates:
                        logging.info(f"🔄 Updating criteria for session {session_id}: {updates}")
                        try:
                            # Some ConversationMemory implementations might use update_criteria or set_criteria
                            if hasattr(memory, "update_criteria"):
                                memory.update_criteria(session_id, updates)
                                logging.debug(f"✅ Session {session_id} criteria updated with {updates}")
                            elif hasattr(memory, "set_criteria"):
                                memory.set_criteria(session_id, updates)
                                logging.debug(f"✅ Session {session_id} criteria set with {updates}")
                            else:
                                logging.warning("⚠️ ConversationMemory missing update_criteria / set_criteria methods.")
                        except Exception as mem_exc:
                            logging.exception(f"❌ Failed to update memory criteria for session {session_id}: {mem_exc}")
                except json.JSONDecodeError:
                    logging.warning(
                        f"Could not parse JSON from agent response: {result_str_json}"
                    )
                    # agent_response remains the fallback

            # Retrieve updated session state
            updated_session = memory.get_session(session_id)
            all_criteria_ready = memory.is_ready_to_search(session_id)

            # [MODIFIED] Handle automatically triggering search (Flow Steps 4-6)
            if (
                updated_session
                and all_criteria_ready
                and updated_session["status"]
                not in [
                    "searching",
                    "AWAITING_APPLY_DECISION",
                    "COMPLETED_NO_APPLY",
                    "APPLY_APPROVED",
                ]
            ):
                logging.info(
                    "All criteria collected! Queueing background search job..."
                )

                search_criteria = updated_session["criteria"]
                memory.update_status(session_id, "searching")

                # Create job row and launch background worker
                job_id = _create_job(session_id=session_id, job_type="search")
                background_tasks.add_task(
                    _run_search_task, job_id, session_id, search_criteria
                )

                started_msg = "Alright, I’ve gathered all the information. Starting the search for you now! This may take about a minute…"
                memory.add_message(
                    session_id,
                    "assistant",
                    started_msg,
                    {"action": "search_started", "job_id": job_id},
                )

                return JSONResponse(
                    status_code=http_status.HTTP_202_ACCEPTED,
                    content={
                        "success": True,
                        "status": "SEARCH_STARTED",
                        "session_id": session_id,
                        "job_id": job_id,
                        "response": started_msg,
                        "criteria": updated_session["criteria"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

            # Standard conversational reply (still collecting criteria)
            memory.add_message(
                session_id,
                "assistant",
                agent_response,
                {"extracted_criteria": extracted_criteria, "is_complete": is_complete},
            )

            # Fetch session after agent reply
            updated_session = memory.get_session(session_id)

            if updated_session:
                return {
                    "success": True,
                    "session_id": session_id,
                    "response": agent_response,
                    "criteria": updated_session["criteria"],
                    "extracted_criteria": extracted_criteria,
                    "search_criteria": updated_session["criteria"],
                    "is_complete": is_complete or memory.is_ready_to_search(session_id),
                    "status": updated_session["status"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            # Fallback response when session is missing
            return {
                "success": True,
                "session_id": session_id,
                "response": agent_response,
                "criteria": {},
                "extracted_criteria": extracted_criteria,
                "search_criteria": {},
                "is_complete": is_complete or memory.is_ready_to_search(session_id),
                "status": "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except json.JSONDecodeError as e:
            # If JSON parsing fails, return plain text reply
            logging.warning(f"Failed to parse JSON from agent response: {e}")
            agent_response = result_str if result_str else str(result)
            memory.add_message(session_id, "assistant", agent_response)
            updated_session = memory.get_session(session_id)
            # (Removed unused local variables 'status' and 'criteria' to satisfy linter.)

            if updated_session:
                return {
                    "success": True,
                    "session_id": session_id,
                    "response": agent_response,
                    "criteria": updated_session["criteria"],
                    "extracted_criteria": {},
                    "search_criteria": updated_session["criteria"],
                    "is_complete": memory.is_ready_to_search(session_id),
                    "status": updated_session["status"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            return {
                "success": True,
                "session_id": session_id,
                "response": agent_response,
                "criteria": {},
                "extracted_criteria": {},
                "search_criteria": {},
                "is_complete": memory.is_ready_to_search(session_id),
                "status": "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    except Exception as e:
        logging.error(f"Error in agent_housing_chat: {e}", exc_info=True)
        return {
            "success": False,
            "session_id": session_id if 'session_id' in locals() else None,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.post("/agent/housing/reason_link")
def agent_reason_link(request: dict):
    """
    Reason about a housing listing URL and extract search parameters with mandatory commute inference.
    
    Features:
    1. Analyze housing listing URLs using AI reasoning
    2. Extract: city, price, min_size
    3. ALWAYS infer commute_target (never null) using geographic and contextual reasoning
    4. Return structured JSON ready for housing_search
    
    Parameters:
    - url: The housing listing URL to analyze (required)
    
    Returns:
    - Structured JSON with city, price, min_size, commute_target (always inferred)
    """
    try:
        url = request.get("url")
        if not url:
            return JSONResponse(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "error": "URL is required",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        
        # Check if agent features are available
        if not AGENT_AVAILABLE:
            return JSONResponse(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "error": "Web reasoning agent unavailable: missing or invalid configuration (e.g. OPENAI_API_KEY).",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        
        # Build crew inputs
        crew_inputs = {"url": url}
        
        logging.info(f"Starting web reasoning for URL: {url}")
        result = run_main_crew("web_reason", crew_inputs, streamlit_callback=None)
        
        # Parse the result
        try:
            parsed_result = _parse_agent_result(result)
            
            # Extract search parameters from the parsed result
            search_params = {}
            if isinstance(parsed_result, dict):
                search_params = parsed_result
            elif isinstance(parsed_result, str):
                # Try to parse as JSON
                try:
                    search_params = json.loads(parsed_result)
                except json.JSONDecodeError:
                    # Extract from text if JSON parsing fails
                    search_params = {"raw_response": parsed_result}
            
            # Validate that all required fields are present
            required_fields = ["city", "price", "min_size", "commute_target"]
            missing_fields = [f for f in required_fields if f not in search_params]
            
            if missing_fields:
                logging.warning(f"Missing required fields in reasoning result: {missing_fields}")
                # Try to extract from raw response
                if "raw_response" not in search_params:
                    search_params["raw_response"] = str(result)
            
            return {
                "success": True,
                "url": url,
                "search_params": search_params,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
        except Exception as parse_error:
            logging.error(f"Error parsing web reasoning result: {parse_error}", exc_info=True)
            return {
                "success": True,
                "url": url,
                "search_params": {"raw_response": str(result)},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    
    except Exception as e:
        logging.error(f"Error in agent_reason_link: {e}", exc_info=True)
        return JSONResponse(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


@app.post("/agent/housing/analyze_link")
def agent_analyze_link(request: dict):
    """
    Analyze and extract structured data from an arbitrary URL.
    
    Features:
    1. Extract data from property listings, LinkedIn profiles, or general web pages.
    2. Auto-detect content type and extract relevant fields.
    3. Present structured JSON data for user confirmation.
    4. Optionally trigger housing_search for confirmed property listings.
    
    Parameters:
    - url: The URL to analyze (required)
    - confirmed: Whether user has confirmed the data (default: false)
    - extract_type: Type of content if already known (optional)
    - Additional fields if confirmed (city, price, size, etc.)
    
    Returns:
    - Extracted structured data as JSON
    - Confirmation status and next steps
    """
    try:
        url = request.get("url")
        if not url:
            return JSONResponse(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "error": "URL is required",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        
        # Check if agent features are available
        if not AGENT_AVAILABLE:
            return JSONResponse(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "error": "Web analysis agent unavailable: missing or invalid configuration (e.g. OPENAI_API_KEY).",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        
        # Build crew inputs
        crew_inputs = {
            "url": url,
            "confirmed": request.get("confirmed", False),
            "extract_type": request.get("extract_type"),
            # Additional fields for confirmed property search
            "city": request.get("city"),
            "price": request.get("price"),
            "max_price": request.get("max_price"),
            "size_m2": request.get("size_m2"),
            "min_size": request.get("min_size"),
            "location": request.get("location"),
            "commute_target": request.get("commute_target"),
        }
        
        logging.info(f"Starting web analysis for URL: {url} (confirmed={crew_inputs['confirmed']})")
        result = run_main_crew("web_analysis", crew_inputs, streamlit_callback=None)
        
        # Parse the result
        try:
            parsed_result = _parse_agent_result(result)
            
            # Extract data from the parsed result
            extracted_data = {}
            if isinstance(parsed_result, dict):
                extracted_data = parsed_result
            elif isinstance(parsed_result, str):
                # Try to parse as JSON
                try:
                    extracted_data = json.loads(parsed_result)
                except json.JSONDecodeError:
                    extracted_data = {"raw_response": parsed_result}
            
            return {
                "success": True,
                "url": url,
                "data": extracted_data,
                "confirmed": crew_inputs["confirmed"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
        except Exception as parse_error:
            logging.error(f"Error parsing web analysis result: {parse_error}", exc_info=True)
            return {
                "success": True,
                "url": url,
                "data": {"raw_response": str(result)},
                "confirmed": crew_inputs["confirmed"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    
    except Exception as e:
        logging.error(f"Error in agent_analyze_link: {e}", exc_info=True)
        return JSONResponse(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


@app.get("/agent/housing/sessions")
def list_conversation_sessions(limit: int = 10):
    """List all conversation sessions"""
    try:
        memory = ConversationMemory()
        sessions = memory.list_sessions(limit=limit)

        return {
            "success": True,
            "count": len(sessions),
            "sessions": sessions,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logging.error(f"Error listing sessions: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.get("/health")
def health():
    """Simple health check endpoint including agent availability."""
    return {
        "status": "ok",
        "agent_available": AGENT_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/agent/housing/session/{session_id}")
def get_conversation_session(session_id: str):
    """Get details of a specific conversation session"""
    try:
        memory = ConversationMemory()
        session = memory.get_session(session_id)

        if not session:
            return {
                "success": False,
                "error": f"Session {session_id} not found",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "success": True,
            "session": session,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logging.error(f"Error getting session: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ---------- Geocoding endpoints ----------


class GeocodeRequest(BaseModel):
    address: str


class GeocodeResponse(BaseModel):
    address: str
    latitude: float
    longitude: float
    cached: bool


def hash_address(address: str) -> str:
    """Generate a hash for address caching."""
    return hashlib.sha256(address.lower().strip().encode()).hexdigest()


@app.post("/geocode", response_model=GeocodeResponse)
async def geocode_address(request: GeocodeRequest):
    """
    Geocode an address using Google Geocoding API with caching.
    Returns latitude and longitude coordinates.
    """
    address = request.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address cannot be empty")

    address_hash = hash_address(address)

    # Check cache first
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT address, latitude, longitude FROM address_cache WHERE address_hash = ?",
            (address_hash,),
        )
        cached = cur.fetchone()

        if cached:
            return GeocodeResponse(
                address=cached["address"],
                latitude=cached["latitude"],
                longitude=cached["longitude"],
                cached=True,
            )

    # Call Google Geocoding API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "address": address,
                    "key": GOOGLE_MAPS_API_KEY,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logging.error("Geocoding API request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")

    if data.get("status") != "OK":
        logging.warning(
            "Geocoding failed for address '%s': %s", address, data.get("status")
        )
        raise HTTPException(
            status_code=404, detail=f"Address not found: {data.get('status')}"
        )

    results = data.get("results", [])
    if not results:
        raise HTTPException(status_code=404, detail="No geocoding results found")

    location = results[0]["geometry"]["location"]
    latitude = location["lat"]
    longitude = location["lng"]

    # Cache the result
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO address_cache (address_hash, address, latitude, longitude, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(address_hash) DO UPDATE SET
                address = excluded.address,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                created_at = excluded.created_at
            """,
            (address_hash, address, latitude, longitude, now),
        )
        conn.commit()

    return GeocodeResponse(
        address=address,
        latitude=latitude,
        longitude=longitude,
        cached=False,
    )


# ---------- Image serving endpoint ----------
@app.get("/images/{listing_id}/thumbnail.webp")
async def serve_thumbnail(listing_id: str):
    """Serve thumbnail images for listings."""
    # Construct the path to the image
    image_path = os.path.join("images", listing_id, "thumbnail.webp")

    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(
        image_path,
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
        },
    )


# --- [NEW] Endpoint to serve application proof (Flow Step 10) ---
@app.get("/application/proof/{external_id}")
async def get_application_proof(external_id: str):
    """
    Serve the saved screenshot proof for an applied listing.
    """
    screenshot_path = None
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT application_screenshot_path FROM listings WHERE external_id = ?",
                (external_id,),
            )
            row = cur.fetchone()
            if row:
                screenshot_path = row["application_screenshot_path"]

    except Exception as e:
        logging.error(
            f"Database error while fetching screenshot path for {external_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Database error")

    if not screenshot_path:
        raise HTTPException(
            status_code=404, detail="No application proof found for this listing."
        )

    # [MODIFIED] Check path assuming API is run from project root
    # (where 'outputs' directory lives)
    if not os.path.exists(screenshot_path):
        logging.error(
            f"File not found at path: {screenshot_path} (External ID: {external_id})"
        )
        raise HTTPException(
            status_code=404, detail="Application proof file not found on server."
        )

    return FileResponse(
        screenshot_path,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=3600",  # Cache for 1 hour
        },
    )
