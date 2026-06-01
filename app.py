from __future__ import annotations

import asyncio
import os
import time
import logging
import hashlib
from datetime import datetime
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
)
from linebot.v3.webhooks import MessageEvent

# โมดูลที่แยกสัดส่วน (Modularized imports)
from db.database import (
    SessionLocal,
    engine,
    check_db_health,
    DATABASE_URL,
    IS_FALLBACK_MODE,
    DB_DIALECT,
)
from db.models import Base
from handlers.message_handler import handle_webhook_event

# บันทึกเวลาเริ่มระบบเพื่อทำ Observability
START_TIME = time.time()
BANGKOK = ZoneInfo("Asia/Bangkok")
VERSION = "1.1.0"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================================================
# LINE Config
# =========================================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]

line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)

# Lazy-initialize inside lifespan to avoid "RuntimeError: no running event loop" at module load
api_client: AsyncApiClient | None = None
line_api: AsyncMessagingApi | None = None

# =========================================================
# Webhook Deduplication Protection
# =========================================================
recent_events: dict[str, float] = {}
DEDUP_TTL = 300       # วินาที
DEDUP_MAX_SIZE = 1000 # จำกัดขนาดป้องกัน memory leak
recent_events_lock = asyncio.Lock()

async def is_event_duplicate(dedup_id: str) -> bool:
    async with recent_events_lock:
        now = time.time()

        # ลบ entry ที่หมดอายุ
        expired = [k for k, v in recent_events.items() if now - v > DEDUP_TTL]
        for k in expired:
            del recent_events[k]

        # ถ้า dict ใหญ่เกิน ลบ entry เก่าสุดออก
        if len(recent_events) >= DEDUP_MAX_SIZE:
            oldest = min(recent_events, key=recent_events.get)
            del recent_events[oldest]

        if dedup_id in recent_events:
            return True

        recent_events[dedup_id] = now
        return False

# =========================================================
# FastAPI App Lifespan
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global api_client, line_api
    
    # Initialize LINE clients inside the running asyncio event loop
    api_client = AsyncApiClient(line_config)
    line_api = AsyncMessagingApi(api_client)

    # Startup
    async with engine.begin() as conn:
        # [P0 STARTUP SELECT 1] Fail-Fast บูตระบบไม่ผ่านทันทีหาก DATABASE_URL มีปัญหา
        from sqlalchemy import text
        try:
            await conn.execute(text("SELECT 1"))
            logger.info("Startup database validation (SELECT 1) succeeded.")
        except Exception as e:
            logger.critical(f"FATAL: Startup database validation failed! Connection refused: {e}")
            raise e

        # WAL mode: ช่วยลด lock contention ถ้าใช้ SQLite ในเครื่อง
        if DATABASE_URL.startswith("sqlite"):
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000;")
        
        # สร้างตารางอัตโนมัติ (ปลอดภัยทั้ง SQLite และ Supabase)
        await conn.run_sync(Base.metadata.create_all)
        
    logger.info("Database connection and tables initialized.")
    logger.info(
        f"DiaryBot started | db={DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL} | tz={BANGKOK}"
    )

    yield

    # Shutdown
    if api_client:
        await api_client.close()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(title="DiaryBot", lifespan=lifespan)

# =========================================================
# API Endpoints
# =========================================================

@app.get("/ping")
async def ping():
    return {
        "status": "ok",
        "version": VERSION,
        "time": datetime.now(BANGKOK).isoformat(),
        "tz": str(BANGKOK),
    }


@app.get("/debug/test-period")
async def debug_test_period():
    """[TEMP DEBUG] สั่งรัน Unit Test ของ Period Aggregation บนสภาพแวดล้อม Render จริง"""
    import unittest
    import io
    import traceback
    
    try:
        from tests.test_period import TestPeriodSummaryAggregation
        
        suite = unittest.TestLoader().loadTestsFromTestCase(TestPeriodSummaryAggregation)
        stream = io.StringIO()
        runner = unittest.TextTestRunner(stream=stream, verbosity=2)
        result = runner.run(suite)
        
        stream.seek(0)
        output = stream.read()
        
        return {
            "status": "ok" if result.wasSuccessful() else "failed",
            "tests_run": result.testsRun,
            "errors": len(result.errors),
            "failures": len(result.failures),
            "output": output
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }


@app.get("/health")
async def health():
    """เช็คสุขภาพของระบบและฐานข้อมูล พร้อมส่งค่า uptime และเวลาเริ่มรันจริง"""
    db_ok = await check_db_health()
    uptime_sec = time.time() - START_TIME
    uptime_hours = round(uptime_sec / 3600.0, 2)
    started_at = datetime.fromtimestamp(START_TIME, tz=BANGKOK).isoformat()

    if db_ok:
        if IS_FALLBACK_MODE:
            status_str = "degraded"
            db_str = "sqlite"
        else:
            status_str = "ok"
            db_str = DB_DIALECT
        status_code = 200
    else:
        status_str = "error"
        db_str = "disconnected"
        status_code = 500

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status_str,
            "database": db_str,
            "fallback_mode": IS_FALLBACK_MODE,
            "uptime_hours": uptime_hours,
            "started_at": started_at,
        }
    )


@app.post("/callback")
async def callback(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    try:
        events = parser.parse(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=401, detail="invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue

        # [P1 DEDUP BY LINE EVENT ID] ตรวจเช็คการทำซ้ำจาก ID ประจำตัวของ LINE โดยตรง
        event_id = getattr(event, "webhook_event_id", None)
        if event_id:
            if await is_event_duplicate(event_id):
                logger.info(f"Duplicate LINE Event ID {event_id} ignored")
                continue
        else:
            # Fallback ไปลัด hash body ดั้งเดิมหากไม่พบ ID
            body_hash = hashlib.sha256(body).hexdigest()
            if await is_event_duplicate(body_hash):
                logger.info("Duplicate body hash ignored")
                continue

        async with SessionLocal() as db:
            await handle_webhook_event(event, db, line_api)

    return {"status": "ok"}
