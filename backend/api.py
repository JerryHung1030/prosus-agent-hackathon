# api.py
from datetime import datetime, timezone
import logging
from typing import Optional, List, Literal, Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr

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
@app.post("/ingest-listings")
def ingest_listings(items: List[ListingIn]):
    """
    Batch receive listings and write to SQLite.
    - No compare/update: every listing is directly added.
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

            cur.execute("""
                INSERT INTO listings (
                    external_id, url, title,
                    price_amount, price_frequency, service_costs,
                    area_m2, street, neighborhood, city, postal_code,
                    housing_type, furnishes, deposit,
                    contract_start_date, contract_duration_months,
                    agency_name, agency_email, agency_contact_url,
                    first_seen, pets_allowed, scraper_version,
                    thumbnail_path, raw_json, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                json.dumps(it.model_dump(by_alias=True, exclude_none=True)),
                now,
                now,
            ))
            inserted += 1

        conn.commit()

    return {"inserted": inserted, "total": len(items)}


@app.get("/listings")
def list_listings(
    limit: int = 50,
    offset: int = 0,
    city: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    pets_allowed: Optional[bool] = None,
    since: Optional[str] = None,                 # ISO date string, filters first_seen >= since
    q: Optional[str] = None,                     # Keyword search: title/street/neighborhood/city
    order_by: Literal["first_seen","price_amount","area_m2","updated_at","created_at","id"] = "first_seen",
    order_dir: Literal["asc","desc"] = "desc",
    include_raw: bool = False,
):
    limit = max(1, min(limit, 200))  # Hard limit to avoid too large value
    offset = max(0, offset)

    cols = [
        "id", "external_id", "url", "title",
        "price_amount", "price_frequency", "service_costs",
        "area_m2", "street", "neighborhood", "city", "postal_code",
        "housing_type", "furnishes", "deposit",
        "contract_start_date", "contract_duration_months",
        "agency_name", "agency_email",
    "agency_contact_url",
        "first_seen", "pets_allowed",
        "scraper_version", "thumbnail_path", "created_at", "updated_at"
    ]
    if include_raw:
        cols.append("raw_json")

    where = []
    params: List[object] = []

    if city:
        where.append("city = ?")
        params.append(city)

    if min_price is not None:
        where.append("price_amount >= ?")
        params.append(min_price)

    if max_price is not None:
        where.append("price_amount <= ?")
        params.append(max_price)

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

    # total count
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS c FROM listings {where_sql}", params)
        total = cur.fetchone()["c"]

        # page data
        cur.execute(
            f"""
            SELECT {", ".join(cols)}
            FROM listings
            {where_sql}
            ORDER BY {order_by} {order_dir}
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )
        items = [dict(r) for r in cur.fetchall()]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


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