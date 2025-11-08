# api.py
from datetime import datetime, timezone
import hashlib
import logging
import math
import os
from typing import Optional, List, Literal, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, EmailStr
import httpx

from db import get_connection, init_db
import json

app = FastAPI(title="Listings API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

init_db()  # Ensure tables exist on startup

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
    status: str = "running"   # default running
    start_time: Optional[str] = None  # can be passed by LLM, otherwise use current time


class LLMFinishIn(BaseModel):
    job_id: int
    status: str               # finished / error
    result: Optional[Dict[str, Any]] = None  # JSON object: {"text": "...", "image_path": "..."}
    end_time: Optional[str] = None

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
        logging.warning("Geocoding failed for address '%s': %s", address, data.get("status"))
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
                    logging.info("Geocoded listing %s: %.6f, %.6f", it.id, latitude, longitude)
                else:
                    logging.warning("Failed to geocode listing %s with address: %s", it.id, full_address)

            cur.execute("""
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
            """, (
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
                1 if it.pets_allowed else 0 if it.pets_allowed is not None else None,
                meta.scraper_version,
                it.thumbnail_path,
                latitude,
                longitude,
                json.dumps(it.model_dump(by_alias=True, exclude_none=True)),
                now,
                now,
            ))
            inserted += 1

        conn.commit()

    return {"inserted": inserted, "total": len(items)}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points on Earth using haversine formula. Returns km."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@app.get("/listings")
def list_listings(
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
    order_by: Literal["first_seen","price_amount","area_m2","updated_at","created_at","id","distance"] = "first_seen",
    order_dir: Literal["asc","desc"] = "desc",
    include_raw: bool = False,
    fetch_all: bool = Query(False, alias="all"),
):
    """
    List listings with optional filtering by:
    - city: fuzzy match on city name
    - lat/lng/radius_km: geo-based filtering (all 3 required together)
    - price, area, pets, etc.
    
    If lat/lng/radius_km are provided, results are sorted by distance and include distance_km field.
    """
    offset = max(0, offset)
    limit = max(1, min(limit, 200))

    cols = [
        "id", "external_id", "url", "title",
        "price_amount", "price_frequency", "service_costs",
        "area_m2", "street", "neighborhood", "city", "postal_code",
        "housing_type", "furnishes", "deposit",
        "contract_start_date", "contract_duration_months",
        "agency_name", "agency_email", "agency_contact_url",
        "first_seen", "pets_allowed",
        "scraper_version", "thumbnail_path", "latitude", "longitude",
        "created_at", "updated_at"
    ]
    if include_raw:
        cols.append("raw_json")

    where = []
    params: List[object] = []
    
    use_geo_filter = lat is not None and lng is not None and radius is not None

    if use_geo_filter:
        # Filter by lat/lng with bounding box for efficiency, then compute exact distance
        # Rough bounding box: 1 degree ~ 111km
        lat_delta = radius / 111.0
        lng_delta = radius / (111.0 * math.cos(math.radians(lat)))
        
        where.append("latitude IS NOT NULL")
        where.append("longitude IS NOT NULL")
        where.append("latitude BETWEEN ? AND ?")
        params.extend([lat - lat_delta, lat + lat_delta])
        where.append("longitude BETWEEN ? AND ?")
        params.extend([lng - lng_delta, lng + lng_delta])

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
        where.append("(title LIKE ? OR street LIKE ? OR neighborhood LIKE ? OR city LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with get_connection() as conn:
        cur = conn.cursor()
        
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
            items_with_distance = []
            for row in rows:
                if row["latitude"] is not None and row["longitude"] is not None:
                    dist = haversine(lat, lng, row["latitude"], row["longitude"])
                    if dist <= radius:
                        row["distance_km"] = round(dist, 2)
                        row["location"] = {"lat": row["latitude"], "lng": row["longitude"]}
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
            items = items[offset:offset + limit]
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


# ---------- Geocoding endpoints ----------
GOOGLE_MAPS_API_KEY = "AIzaSyBWFfsY7vVUGNEtNLd9xT7gZfuOs3EBIPM"


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
        logging.warning("Geocoding failed for address '%s': %s", address, data.get("status"))
        raise HTTPException(status_code=404, detail=f"Address not found: {data.get('status')}")
    
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