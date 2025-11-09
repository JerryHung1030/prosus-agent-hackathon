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
from db import get_connection, init_db
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field

app = FastAPI(title="Listings API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()  # Ensure tables exist on startup

# Import agent runner from sibling src/ package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.main import run_main_crew


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
    status: str = "running"  # default running
    start_time: Optional[str] = None  # can be passed by LLM, otherwise use current time


class LLMFinishIn(BaseModel):
    job_id: int
    status: str  # finished / error
    result: Optional[Dict[str, Any]] = (
        None  # JSON object: {"text": "...", "image_path": "..."}
    )
    end_time: Optional[str] = None


# ---------- Agent Housing Search models ----------
class HousingSearchRequest(BaseModel):
    city: Optional[str] = Field(None, description="城市名稱，例如：Amsterdam")
    max_price: Optional[int] = Field(None, description="最高價格")
    min_size: Optional[int] = Field(None, description="最小面積（平方米）")
    commute_target: Optional[str] = Field(None, description="通勤目的地地址")


class HousingApplyRequest(BaseModel):
    user_profile: Dict[str, Any] = Field(..., description="用戶個人資料")
    listing_details: Dict[str, Any] = Field(..., description="房源詳細資料")


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
    """Calculate distance between two points on Earth using haversine formula. Returns km."""
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
    ]
    if include_raw:
        cols.append("raw_json")

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


# ---------- Agent Housing endpoints ----------


@app.post("/agent/housing/search")
def agent_housing_search(request: HousingSearchRequest):
    """
    使用 AI Agent 搜尋和排名房源

    功能：
    1. 使用 Search Agent 從資料庫獲取符合條件的房源
    2. 使用 Ranking Agent 計算通勤時間並排名前 5 個房源

    參數：
    - city: 城市名稱（可選）
    - max_price: 最高價格（可選）
    - min_size: 最小面積（可選）
    - commute_target: 通勤目的地地址（可選）

    返回：
    - 前 5 個排名的房源，包含 match_score 和 commute_time
    """
    try:
        # 構建搜尋條件
        criteria = {
            "city": request.city,
            "price": request.max_price,
            "size": request.min_size,
            "commute_target": request.commute_target or "Amsterdam Central Station",
        }

        # 準備 crew 輸入
        crew_inputs = {"criteria": criteria}

        # 執行 housing_search crew（包含 Search Agent 和 Ranking Agent）
        logging.info(f"Starting housing search with criteria: {criteria}")
        result = run_main_crew("housing_search", crew_inputs, streamlit_callback=None)

        # 解析結果
        try:
            # 嘗試從不同的格式解析結果
            result_str = None
            parsed_result = None

            # CrewAI 可能返回不同的格式
            # 1. 嘗試 json_dict 屬性
            if hasattr(result, "json_dict"):
                try:
                    if result.json_dict:
                        parsed_result = result.json_dict
                        result_str = json.dumps(parsed_result)
                except Exception:
                    pass

            # 2. 如果還沒有結果，嘗試 raw 屬性（最常見）
            if not parsed_result and hasattr(result, "raw"):
                try:
                    result_str = result.raw
                except Exception:
                    pass

            # 3. 如果還沒有結果，嘗試 str()
            if not parsed_result and not result_str:
                result_str = str(result)

            # 如果 result_str 是字串，嘗試解析 JSON
            if isinstance(result_str, str) and not parsed_result:
                # 嘗試提取 JSON（可能包含在文字中）
                import re

                # 尋找 JSON 陣列或物件
                json_match = re.search(r"(\[.*\]|\{.*\})", result_str, re.DOTALL)
                if json_match:
                    result_str = json_match.group(1)

                parsed_result = json.loads(result_str)

            # 處理不同的返回格式
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

            return {
                "success": True,
                "criteria": criteria,
                "count": len(listings),
                "listings": listings,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            logging.error(f"Failed to parse agent result as JSON: {e}")
            # 如果解析失敗，返回原始結果
            raw_output = str(result)
            return {
                "success": False,
                "error": f"Failed to parse agent result: {str(e)}",
                "raw_result": raw_output[:500],  # 只返回前 500 字元避免太長
                "hint": "Agent 可能返回了非 JSON 格式的結果，請檢查 Task 設定",
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
def agent_housing_apply(request: HousingApplyRequest):
    """
    使用 AI Agent 自動申請房源

    功能：
    1. 使用 Apply Agent 生成個性化的動機信
    2. 自動填寫申請表單並提交
    3. 截圖保存申請證明

    參數：
    - user_profile: 用戶個人資料（包含姓名、email、電話等）
    - listing_details: 房源詳細資料

    返回：
    - 申請結果和截圖路徑
    """
    try:
        # 準備 crew 輸入
        crew_inputs = {
            "user_profile": json.dumps(request.user_profile),
            "listing_details": json.dumps(request.listing_details),
        }

        # 執行 housing_apply crew（Apply Agent）
        logging.info(
            f"Starting housing application for listing: {request.listing_details.get('title', 'N/A')}"
        )
        result = run_main_crew("housing_apply", crew_inputs, streamlit_callback=None)

        # 解析結果
        result_text = None
        if hasattr(result, "raw") and isinstance(result.raw, str):
            result_text = result.raw
        else:
            try:
                result_text = str(result)
            except Exception:
                result_text = ""

        # 嘗試提取截圖路徑
        screenshot_path = None
        if isinstance(result_text, str) and "Screenshot saved as " in result_text:
            try:
                path_part = (
                    result_text.split("Screenshot saved as ")[-1].strip().rstrip(".")
                )
                if os.path.exists(path_part) and path_part.endswith(".png"):
                    screenshot_path = path_part
            except Exception as e:
                logging.error(f"Error parsing screenshot path: {e}")

        return {
            "success": True,
            "message": result_text,
            "screenshot_path": screenshot_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logging.error(f"Error in agent_housing_apply: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.post("/agent/housing/chat")
def agent_housing_chat(session_id: Optional[str] = None, message: str = ""):
    """
    對話式房源搜尋

    功能：
    1. 與用戶進行自然對話
    2. 逐步收集房源搜尋條件（城市、價格、面積、通勤地點）
    3. 儲存對話歷史
    4. 當資訊完整時自動觸發搜尋

    參數：
    - session_id: 會話 ID（可選，如果是新對話則不提供）
    - message: 用戶訊息

    返回：
    - Agent 的回覆和更新的會話狀態
    """
    try:
        from src.memory import ConversationMemory

        # 初始化記憶體
        memory = ConversationMemory()

        # 如果沒有 session_id，創建新會話
        if not session_id:
            session_id = memory.create_session()
            logging.info(f"Created new conversation session: {session_id}")

        # 獲取會話
        session = memory.get_session(session_id)
        if not session:
            return {
                "success": False,
                "error": f"Session {session_id} not found",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # 儲存用戶訊息
        memory.add_message(session_id, "user", message)

        # 準備對話上下文
        conversation_history = memory.format_conversation_history(session_id, limit=10)
        current_criteria = memory.get_criteria(session_id)

        crew_inputs = {
            "session_id": session_id,
            "message": message,
            "conversation_history": conversation_history,
            "current_criteria": current_criteria,
        }

        # 執行對話 Agent
        logging.info(f"Processing conversation for session {session_id}")
        logging.info(f"Current criteria: {current_criteria}")
        result = run_main_crew("conversation", crew_inputs, streamlit_callback=None)

        # 解析結果
        try:
            # 檢查 result 物件的所有屬性
            print(f"\n{'='*60}")
            print("DEBUG: Result object attributes:")
            print(
                f"  - dir(result): {[attr for attr in dir(result) if not attr.startswith('_')]}"
            )
            print(f"{'='*60}\n")

            result_str = None
            if hasattr(result, "raw"):
                result_str = result.raw
            else:
                result_str = str(result)

            logging.info(f"Agent result (first 1000 chars): {result_str[:1000]}")

            # 檢查是否有 tasks_output 或其他包含工具輸出的屬性
            tasks_output_str = ""
            if hasattr(result, "tasks_output"):
                tasks_output_str = str(result.tasks_output)
                print(
                    f"\nDEBUG: tasks_output (first 500 chars): {tasks_output_str[:500]}\n"
                )

            # 也檢查完整的 result 物件（工具輸出可能在其他屬性）
            full_result_str = str(result)
            logging.info(
                f"Full result object (first 1000 chars): {full_result_str[:1000]}"
            )

            # 檢查是否觸發了搜尋（工具可能返回了 TRIGGER_SEARCH）
            import re

            # 先解析並更新 criteria，再檢查是否完整
            # 提取 JSON
            json_match = re.search(r"\{.*\}", result_str, re.DOTALL)
            if json_match:
                result_str_json = json_match.group(0)
                try:
                    parsed_result = json.loads(result_str_json)
                    extracted_criteria = parsed_result.get("extracted_criteria", {})

                    # 更新會話中的條件
                    updates = {}
                    for key, value in extracted_criteria.items():
                        if value is not None:
                            updates[key] = value

                    if updates:
                        print(f"\nDEBUG: Updating criteria with: {updates}\n")
                        memory.update_criteria(session_id, updates)
                except json.JSONDecodeError:
                    pass

            # 現在檢查是否所有條件都已收集
            updated_session = memory.get_session(session_id)
            all_criteria_ready = memory.is_ready_to_search(session_id)

            print(f"\n{'='*60}")
            print("DEBUG: Checking if search should be triggered...")
            if updated_session:
                print(f"DEBUG: Current criteria: {updated_session['criteria']}")
                print(f"DEBUG: All criteria ready: {all_criteria_ready}")
                print(f"DEBUG: Session status: {updated_session['status']}")
            else:
                print("DEBUG: Session no longer available.")
            print(f"{'='*60}\n")

            # 如果所有條件都收集完成且還沒搜尋過，自動觸發搜尋
            if (
                updated_session
                and all_criteria_ready
                and updated_session["status"]
                not in [
                    "searching",
                    "completed",
                ]
            ):
                logging.info("All criteria collected! Auto-triggering search...")
                print("\n🎯 ALL CRITERIA COLLECTED! Starting search...\n")

                # 直接使用 memory 中的 criteria
                search_criteria = updated_session["criteria"]

                try:
                    logging.info(
                        f"Triggering housing search with criteria: {search_criteria}"
                    )

                    # 更新會話狀態為搜尋中
                    memory.update_status(session_id, "searching")

                    # 執行搜尋
                    search_result = run_main_crew(
                        "housing_search",
                        {"criteria": search_criteria},
                        streamlit_callback=None,
                    )

                    # 解析搜尋結果
                    search_result_str = None
                    if hasattr(search_result, "raw"):
                        search_result_str = search_result.raw
                    else:
                        search_result_str = str(search_result)

                    # 提取 JSON
                    json_match = re.search(
                        r"(\[.*\]|\{.*\})", search_result_str, re.DOTALL
                    )
                    if json_match:
                        search_result_str = json_match.group(1)

                    search_listings = json.loads(search_result_str)
                    if isinstance(search_listings, dict):
                        search_listings = search_listings.get(
                            "listings", search_listings.get("results", [])
                        )

                    # 儲存搜尋結果
                    memory.save_search_results(session_id, search_listings)

                    agent_response = f"太好了！我已經收集完所有資訊並開始搜尋。找到了 {len(search_listings)} 個符合條件的房源！"

                    memory.add_message(
                        session_id,
                        "assistant",
                        agent_response,
                        {
                            "action": "search_completed",
                            "listings_count": len(search_listings),
                        },
                    )

                    updated_session = memory.get_session(session_id)
                    if updated_session:
                        return {
                            "success": True,
                            "session_id": session_id,
                            "response": agent_response,
                            "criteria": updated_session["criteria"],
                            "is_complete": True,
                            "status": "completed",
                            "search_triggered": True,
                            "listings": search_listings,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    return {
                        "success": True,
                        "session_id": session_id,
                        "response": agent_response,
                        "criteria": {},
                        "is_complete": True,
                        "status": "completed",
                        "search_triggered": True,
                        "listings": search_listings,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                except Exception as e:
                    logging.error(
                        f"Failed to execute search after trigger: {e}", exc_info=True
                    )

            # 正常的對話回覆（還在收集資訊）
            # 提取 JSON
            json_match = re.search(r"\{.*\}", result_str, re.DOTALL)
            if json_match:
                result_str = json_match.group(0)

            parsed_result = json.loads(result_str)

            # 提取 Agent 回覆和條件
            agent_response = parsed_result.get("response", result_str)
            extracted_criteria = parsed_result.get("extracted_criteria", {})
            is_complete = parsed_result.get("is_complete", False)

            # 更新會話中的條件
            updates = {}
            for key, value in extracted_criteria.items():
                if value is not None:
                    updates[key] = value

            if updates:
                memory.update_criteria(session_id, updates)

            # 儲存 Agent 回覆
            memory.add_message(
                session_id,
                "assistant",
                agent_response,
                {"extracted_criteria": extracted_criteria, "is_complete": is_complete},
            )

            # 獲取更新後的會話狀態
            updated_session = memory.get_session(session_id)

            if updated_session:
                return {
                    "success": True,
                    "session_id": session_id,
                    "response": agent_response,
                    "criteria": updated_session["criteria"],
                    "is_complete": is_complete or memory.is_ready_to_search(session_id),
                    "status": updated_session["status"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            return {
                "success": True,
                "session_id": session_id,
                "response": agent_response,
                "criteria": {},
                "is_complete": is_complete or memory.is_ready_to_search(session_id),
                "status": "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except json.JSONDecodeError as e:
            # 如果無法解析 JSON，直接返回文字回覆
            logging.warning(f"Failed to parse JSON from agent response: {e}")
            agent_response = result_str if result_str else str(result)

            memory.add_message(session_id, "assistant", agent_response)

            updated_session = memory.get_session(session_id)

            if updated_session:
                return {
                    "success": True,
                    "session_id": session_id,
                    "response": agent_response,
                    "criteria": updated_session["criteria"],
                    "is_complete": memory.is_ready_to_search(session_id),
                    "status": updated_session["status"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            return {
                "success": True,
                "session_id": session_id,
                "response": agent_response,
                "criteria": {},
                "is_complete": memory.is_ready_to_search(session_id),
                "status": "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    except Exception as e:
        logging.error(f"Error in agent_housing_chat: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.get("/agent/housing/sessions")
def list_conversation_sessions(limit: int = 10):
    """列出所有對話會話"""
    try:
        from src.memory import ConversationMemory

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


@app.get("/agent/housing/session/{session_id}")
def get_conversation_session(session_id: str):
    """獲取特定會話的詳細資訊"""
    try:
        from src.memory import ConversationMemory

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
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


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
