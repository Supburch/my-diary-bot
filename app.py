"""
DiaryBot v3
Production-ready LINE diary bot

Stack:
- FastAPI
- PostgreSQL + SQLAlchemy Async
- Redis
- APScheduler
- Alembic migrations
- LINE Messaging API v3

Changes from v2:
- Removed Base.metadata.create_all → use Alembic
- Added symbol to toggle_habit response
- Pool size tuned for Render free tier (512MB RAM)

Run:
    alembic upgrade head
    gunicorn app:app -k uvicorn.workers.UvicornWorker -w 1 --timeout 120

ENV:
    DATABASE_URL=postgresql+asyncpg://...
    REDIS_URL=redis://...
    LINE_CHANNEL_ACCESS_TOKEN=...
    LINE_CHANNEL_SECRET=...
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from enum import Enum
from typing import AsyncIterator, Optional
from zoneinfo import ZoneInfo

import redis.asyncio as redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# =========================================================
# Config
# =========================================================

class Settings(BaseSettings):
    database_url:              str
    redis_url:                 str
    line_channel_access_token: str
    line_channel_secret:       str

    wake_word:              str = "บอต"
    reminder_hour:          int = 22
    webhook_concurrency:    int = 20   # tuned for Render free (512MB)
    pool_size:              int = 5    # tuned for Render free
    max_overflow:           int = 5
    rate_limit_count:       int = 20
    rate_limit_window_sec:  int = 5
    redis_lock_ttl_sec:     int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator(
        "database_url", "redis_url",
        "line_channel_access_token", "line_channel_secret",
    )
    @classmethod
    def validate_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        return value


settings = Settings()


# =========================================================
# Logging
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("diarybot")


# =========================================================
# Constants
# =========================================================

BANGKOK = ZoneInfo("Asia/Bangkok")

COMMAND_MAP: dict[str, str] = {
    "00": "News/Talk",
    "11": "5min Read",
    "22": "Documentary",
    "33": "PU @ 10",
    "44": "Squad @ 35",
    "55": "Walk 2Km",
    "66": "Trade/Invest",
    "77": "Mindfulness",
    "88": "Farm/House",
    "99": "AI Coding",
}

SUMMARY_CMDS = {"summary", "sum", "สรุป", "วันนี้"}
HELP_CMDS    = {"รหัส", "help", "code", "?"}


# =========================================================
# Database Models
# =========================================================

class Base(DeclarativeBase):
    pass


class DiaryUser(Base):
    __tablename__ = "diary_users"

    user_id: Mapped[str]  = mapped_column(String(255), primary_key=True)
    active:  Mapped[bool] = mapped_column(Boolean, default=True)


class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    id:         Mapped[int]           = mapped_column(primary_key=True)
    user_id:    Mapped[str]           = mapped_column(String(255), index=True)
    entry_date: Mapped[date]          = mapped_column(Date, index=True)
    code:       Mapped[str]           = mapped_column(String(32))
    category:   Mapped[str]           = mapped_column(String(255))
    symbol:     Mapped[str]           = mapped_column(String(8))
    done:       Mapped[bool]          = mapped_column(Boolean, default=True)
    count:      Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note:       Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "entry_date", "code", name="uq_user_date_code"),
    )


# NOTE: ไม่มี Base.metadata.create_all ที่นี่
# schema จัดการด้วย Alembic เท่านั้น (ดู alembic/)

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.pool_size,
    max_overflow=settings.max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# =========================================================
# Redis
# =========================================================

redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
)


async def is_duplicate_event(body: bytes) -> bool:
    digest  = hashlib.sha256(body).hexdigest()
    created = await redis_client.set(f"event:{digest}", "1", ex=300, nx=True)
    return created is None


async def is_rate_limited(user_id: str) -> bool:
    key   = f"rate:{user_id}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, settings.rate_limit_window_sec)
    return count > settings.rate_limit_count


@asynccontextmanager
async def user_lock(user_id: str, ttl: int = settings.redis_lock_ttl_sec) -> AsyncIterator[bool]:
    """Token-safe distributed lock — กัน lock ถูก release โดย request อื่น"""
    key   = f"lock:user:{user_id}"
    token = uuid.uuid4().hex

    acquired = await redis_client.set(key, token, ex=ttl, nx=True)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            current = await redis_client.get(key)
            if current == token:
                await redis_client.delete(key)


# =========================================================
# LINE SDK (reusable client)
# =========================================================

line_config = Configuration(access_token=settings.line_channel_access_token)
line_parser = WebhookParser(settings.line_channel_secret)

line_api_client:    Optional[AsyncApiClient]   = None
line_messaging_api: Optional[AsyncMessagingApi] = None


async def reply_message(reply_token: str, text: str) -> bool:
    try:
        assert line_messaging_api is not None
        await line_messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text[:2000])],
            )
        )
        return True
    except Exception:
        logger.exception("reply_message failed")
        return False


async def push_message(user_id: str, text: str) -> bool:
    try:
        assert line_messaging_api is not None
        await line_messaging_api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=text[:2000])],
            )
        )
        return True
    except Exception:
        logger.exception("push_message failed")
        return False


# =========================================================
# Helpers
# =========================================================

def now_bkk() -> datetime:
    return datetime.now(BANGKOK)

def today_bkk() -> date:
    return now_bkk().date()

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def get_symbol(d: date) -> str:
    return "●" if d.day % 2 == 0 else "■"


async def safe_commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


# =========================================================
# Parser
# =========================================================

class EntryType(str, Enum):
    HABIT   = "habit"
    NOTE    = "note"
    INVALID = "invalid"


def parse_message(text: str) -> dict:
    """
    "55"           → HABIT count=None note=None
    "55 3"         → HABIT count=3    note=None
    "55 วิ่งสวน"   → HABIT count=None note="วิ่งสวน"
    "55 3 วิ่งสวน" → HABIT count=3    note="วิ่งสวน"
    "55 วิ่ง 3 รอบ"→ HABIT count=None note="วิ่ง 3 รอบ"
    "ข้อความ"      → NOTE
    "12 ..."       → INVALID
    """
    text = text.strip()
    if not text:
        return {"type": EntryType.INVALID, "error": "ข้อความว่าง"}

    parts    = text.split(maxsplit=2)
    code     = parts[0]

    if not re.fullmatch(r"\d{2}", code):
        return {"type": EntryType.NOTE, "note": text}

    category = COMMAND_MAP.get(code)
    if not category:
        return {"type": EntryType.INVALID, "error": f"ไม่รู้จักรหัส {code}"}

    count: Optional[int] = None
    note:  Optional[str] = None

    if len(parts) >= 2:
        second = parts[1]
        if re.fullmatch(r"[0-9]+", second):   # ASCII digits only
            count = int(second)
            if count <= 0:
                return {"type": EntryType.INVALID, "error": "จำนวนต้องมากกว่า 0"}
            if count > 1000:
                return {"type": EntryType.INVALID, "error": "จำนวนมากเกินไป"}
            if len(parts) == 3:
                note = parts[2]
        else:
            note = text[len(code):].strip()

    return {"type": EntryType.HABIT, "code": code, "category": category, "count": count, "note": note}


# =========================================================
# Summary & Help
# =========================================================

def build_summary(entries: list[DiaryEntry]) -> str:
    today   = today_bkk()
    symbol  = get_symbol(today)
    outline = "○" if symbol == "●" else "□"

    habit_map  = {e.code: e for e in entries if not e.code.startswith("~~")}
    free_notes = [e.note for e in entries if e.code.startswith("~~") and e.note]

    done_count = 0
    lines = [f"📅 {today.strftime('%d %b %Y')}  ({symbol} = วันนี้)", "─" * 24]

    for code, category in COMMAND_MAP.items():
        entry   = habit_map.get(code)
        is_done = bool(entry and entry.done)
        mark    = symbol if is_done else outline
        if is_done:
            done_count += 1

        extras: list[str] = []
        if is_done and entry and entry.count:
            extras.append(f"×{entry.count}")
        if is_done and entry and entry.note:
            extras.append(entry.note)
        extra = f" · {' | '.join(extras)}" if extras else ""

        lines.append(f"{mark} {code} {category}{extra}")

    if free_notes:
        lines.append("─" * 24)
        for note in free_notes:
            lines.append(f"📝 {note}")

    lines += ["─" * 24, f"✅ {done_count}/{len(COMMAND_MAP)} done"]
    return "\n".join(lines)


def build_help() -> str:
    lines = ["📋 Habit Codes", "─" * 24]
    for code, category in COMMAND_MAP.items():
        lines.append(f"  {code} = {category}")
    lines += [
        "─" * 24,
        "55          → mark done ✅",
        "55 3        → with count",
        "55 วิ่งสวน  → with note",
        "55 (ซ้ำ)   → undo ↩️",
        "~ข้อความ    → free note",
        "สรุป        → today summary",
    ]
    return "\n".join(lines)


# =========================================================
# DB Helpers
# =========================================================

async def register_user(db: AsyncSession, user_id: str) -> None:
    if await db.get(DiaryUser, user_id):
        return
    db.add(DiaryUser(user_id=user_id, active=True))
    try:
        await safe_commit(db)
    except IntegrityError:
        await db.rollback()


async def get_today_entries(db: AsyncSession, user_id: str) -> list[DiaryEntry]:
    result = await db.execute(
        select(DiaryEntry)
        .where(DiaryEntry.user_id == user_id)
        .where(DiaryEntry.entry_date == today_bkk())
        .order_by(DiaryEntry.code)
    )
    return list(result.scalars().all())


# =========================================================
# Business Logic
# =========================================================

async def save_free_note(db: AsyncSession, user_id: str, text: str) -> str:
    note = text.lstrip("~").strip()
    if re.match(r"^note(\s|$)", note, re.IGNORECASE):
        note = note[4:].strip()
    if not note:
        return "❌ ไม่มีข้อความ"

    today = today_bkk()
    db.add(DiaryEntry(
        user_id=user_id, entry_date=today,
        code=f"~~{uuid.uuid4().hex[:8]}",
        category="Free Note", symbol=get_symbol(today),
        done=True, note=note, updated_at=now_utc(),
    ))
    await safe_commit(db)
    return f"📝 {note}"


async def toggle_habit(db: AsyncSession, user_id: str, parsed: dict) -> str:
    today  = today_bkk()
    symbol = get_symbol(today)

    result   = await db.execute(
        select(DiaryEntry)
        .where(DiaryEntry.user_id == user_id)
        .where(DiaryEntry.entry_date == today)
        .where(DiaryEntry.code == parsed["code"])
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.done       = not existing.done
        existing.updated_at = now_utc()
        if existing.done:
            existing.count = parsed["count"]
            existing.note  = parsed["note"]
        else:
            existing.count = None
            existing.note  = None
        await safe_commit(db)

        if existing.done:
            lines = [f"{symbol} {existing.code} {existing.category} ✅"]
            if existing.count:
                lines.append(f"🔢 {existing.count}")
            if existing.note:
                lines.append(f"📝 {existing.note}")
            return "\n".join(lines)
        return f"↩️ ยกเลิก {existing.code} {existing.category}"

    db.add(DiaryEntry(
        user_id=user_id, entry_date=today,
        code=parsed["code"], category=parsed["category"],
        symbol=symbol, done=True,
        count=parsed["count"], note=parsed["note"],
        updated_at=now_utc(),
    ))
    try:
        await safe_commit(db)
    except IntegrityError:
        await db.rollback()
        return "⚠️ มีการอัปเดตพร้อมกัน กรุณาลองใหม่"

    lines = [f"{symbol} {parsed['code']} {parsed['category']} ✅"]
    if parsed["count"]:
        lines.append(f"🔢 {parsed['count']}")
    if parsed["note"]:
        lines.append(f"📝 {parsed['note']}")
    return "\n".join(lines)


async def process_message(db: AsyncSession, user_id: str, text: str) -> str:
    await register_user(db, user_id)

    stripped = text.strip()
    lower    = stripped.lower()

    if lower in SUMMARY_CMDS:
        return build_summary(await get_today_entries(db, user_id))

    if lower in HELP_CMDS:
        return build_help()

    if stripped.startswith("~") or re.match(r"^note(\s|$)", lower):
        return await save_free_note(db, user_id, stripped)

    parsed = parse_message(stripped)

    if parsed["type"] == EntryType.INVALID:
        return f"❌ {parsed['error']}\nพิมพ์ 'รหัส' เพื่อดูรายการ"

    if parsed["type"] == EntryType.NOTE:
        return "👋 DiaryBot\n55 = habit\n~ข้อความ = free note\nสรุป = summary"

    async with user_lock(user_id) as locked:
        if not locked:
            return "⏳ กรุณารอสักครู่"
        return await toggle_habit(db, user_id, parsed)


# =========================================================
# Scheduler
# =========================================================

scheduler = AsyncIOScheduler(timezone="Asia/Bangkok")


async def reminder_job() -> None:
    logger.info("reminder_job started")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(DiaryUser).where(DiaryUser.active.is_(True)))
        users  = list(result.scalars().all())

        for user in users:
            try:
                entries    = await get_today_entries(db, user.user_id)
                done_count = sum(1 for e in entries if e.done and not e.code.startswith("~~"))

                if done_count == 0:
                    await push_message(user.user_id, "🌙 ยังไม่ได้บันทึกเลยวันนี้")
                elif done_count < len(COMMAND_MAP) // 2:
                    await push_message(user.user_id, f"🌙 วันนี้ทำแล้ว {done_count}/{len(COMMAND_MAP)}")
            except Exception:
                logger.exception("reminder_job failed user=%s", user.user_id[:8])


# =========================================================
# FastAPI Lifespan
# =========================================================

@asynccontextmanager
async def lifespan(_: FastAPI):
    global line_api_client, line_messaging_api

    logger.info("starting diarybot v3")

    # Schema managed by Alembic — ไม่ create_all ที่นี่
    line_api_client    = AsyncApiClient(line_config)
    line_messaging_api = AsyncMessagingApi(line_api_client)

    # IMPORTANT: -w 1 เสมอ — APScheduler in-process
    scheduler.add_job(
        reminder_job, "cron",
        hour=settings.reminder_hour, minute=0,
        replace_existing=True,
    )
    scheduler.start()
    logger.info("diarybot v3 started")

    yield

    logger.info("shutdown started")
    scheduler.shutdown(wait=False)
    if line_api_client:
        await line_api_client.close()
    await engine.dispose()
    await redis_client.aclose()
    logger.info("shutdown completed")


# =========================================================
# FastAPI App
# =========================================================

app = FastAPI(title="DiaryBot v3", lifespan=lifespan)

webhook_semaphore = asyncio.Semaphore(settings.webhook_concurrency)


@app.get("/")
async def home():
    return {"status": "running", "version": "3"}


@app.get("/ping")
async def ping():
    return "pong"


@app.get("/health")
async def health():
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        await redis_client.ping()
        return {"status": "ok", "db": "ok", "redis": "ok", "scheduler": scheduler.running}
    except Exception:
        logger.exception("health failed")
        raise HTTPException(status_code=500, detail="unhealthy")


@app.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature", "")
    body      = await request.body()

    if await is_duplicate_event(body):
        return {"status": "duplicate"}

    try:
        events = line_parser.parse(body.decode("utf-8", errors="replace"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="invalid signature")
    except Exception:
        logger.exception("callback parse failed")
        raise HTTPException(status_code=500, detail="parse failed")

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            background_tasks.add_task(handle_event, event)

    return {"status": "ok"}


async def handle_event(event: MessageEvent) -> None:
    async with webhook_semaphore:
        try:
            user_id = event.source.user_id
            text    = event.message.text.strip()

            if event.source.type in ["group", "room"]:
                if not text.startswith(settings.wake_word):
                    return
                text = text[len(settings.wake_word):].strip() or "สรุป"

            if await is_rate_limited(user_id):
                await push_message(user_id, "⚠️ ส่งข้อความเร็วเกินไป")
                return

            async with AsyncSessionLocal() as db:
                response = await process_message(db, user_id, text)

            ok = await reply_message(event.reply_token, response)
            if not ok:
                await push_message(user_id, response)

        except Exception:
            logger.exception("handle_event failed")
