from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from sqlalchemy import Boolean, Date, Integer, String, Text, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# =========================================================
# Config
# =========================================================

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]

DATABASE_URL = "sqlite+aiosqlite:///./diary.db"

BANGKOK = ZoneInfo("Asia/Bangkok")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================================================
# LINE
# =========================================================

line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)
api_client = AsyncApiClient(line_config)
line_api = AsyncMessagingApi(api_client)

# =========================================================
# Database
# =========================================================

class Base(DeclarativeBase):
    pass


class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    code: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(255))
    done: Mapped[bool] = mapped_column(Boolean, default=True)
    count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


engine = create_async_engine(
    DATABASE_URL,
    connect_args={"timeout": 30},
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# =========================================================
# Constants
# =========================================================

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
HELP_CMDS = {"help", "รหัส", "code", "?"}
NOTE_MAX_LEN = 500

# =========================================================
# Duplicate Protection
# =========================================================

recent_events: dict[str, float] = {}
DEDUP_TTL = 300       # วินาที
DEDUP_MAX_SIZE = 1000 # จำกัด size ป้องกัน memory leak


def is_duplicate(body: bytes) -> bool:
    digest = hashlib.sha256(body).hexdigest()
    now = time.time()

    # ลบ entry ที่หมดอายุ
    expired = [k for k, v in recent_events.items() if now - v > DEDUP_TTL]
    for k in expired:
        del recent_events[k]

    # ถ้า dict ใหญ่เกิน ลบ entry เก่าสุดออก
    if len(recent_events) >= DEDUP_MAX_SIZE:
        oldest = min(recent_events, key=recent_events.get)
        del recent_events[oldest]

    if digest in recent_events:
        return True

    recent_events[digest] = now
    return False

# =========================================================
# App (lifespan แทน on_event ที่ deprecated)
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        # WAL mode: ลด lock contention, กัน "database is locked" บน async SQLite
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000;")
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database ready (WAL mode)")
    logger.info(
        "DiaryBot started | db=%s | tz=%s | workers=single",
        DATABASE_URL,
        BANGKOK,
    )

    yield

    # Shutdown
    await api_client.close()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(title="DiaryBot", lifespan=lifespan)

# =========================================================
# Helpers
# =========================================================

def today_bkk() -> date:
    return datetime.now(BANGKOK).date()


def get_symbol(target_date: date) -> str:
    return "●" if target_date.day % 2 == 0 else "■"


async def reply_message(reply_token: str, text: str) -> None:
    await asyncio.wait_for(
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text[:2000])],
            )
        ),
        timeout=10,
    )

# =========================================================
# Parser
# =========================================================

def parse_message(text: str) -> dict:
    text = text.strip()

    if not text:
        return {"type": "invalid"}

    parts = text.split(maxsplit=2)
    code = parts[0]

    if not re.fullmatch(r"\d{2}", code):
        return {"type": "note", "note": text}

    category = COMMAND_MAP.get(code)

    if not category:
        return {"type": "invalid"}

    count = None
    note = None

    if len(parts) == 2:
        if parts[1].isdigit():
            count = int(parts[1])
        else:
            note = parts[1]
    elif len(parts) == 3:
        if parts[1].isdigit():
            count = int(parts[1])
            note = parts[2]
        else:
            # กรณีพิมพ์เป็น "99 บันทึกข้อความ ยาว ยาว" 
            note = text[len(code):].strip()

    return {
        "type": "habit",
        "code": code,
        "category": category,
        "count": count,
        "note": note,
    }

# =========================================================
# Summary
# =========================================================

def build_summary(entries: list[DiaryEntry], target_date: date) -> str:
    symbol = get_symbol(target_date)
    outline = "○" if symbol == "●" else "□"

    habit_map = {
        e.code: e
        for e in entries
        if not e.code.startswith("~~")
    }

    lines = [
        f"📅 {target_date}",
        "─" * 24,
    ]

    done_count = 0

    for code, category in COMMAND_MAP.items():
        entry = habit_map.get(code)

        is_done = bool(entry and entry.done)

        mark = symbol if is_done else outline

        if is_done:
            done_count += 1

        extra = ""

        if is_done and entry and entry.count:
            extra += f" ×{entry.count}"

        if is_done and entry and entry.note:
            extra += f" | {entry.note}"

        lines.append(f"{mark} {code} {category}{extra}")

    lines.append("─" * 24)
    lines.append(f"✅ {done_count}/{len(COMMAND_MAP)}")

    return "\n".join(lines)

# =========================================================
# Business Logic
# =========================================================

async def toggle_habit(
    db: AsyncSession,
    user_id: str,
    parsed: dict,
) -> str:
    today = today_bkk()

    stmt = select(DiaryEntry).where(
        DiaryEntry.user_id == user_id,
        DiaryEntry.entry_date == today,
        DiaryEntry.code == parsed["code"],
    )

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        # ถ้ามีอยู่แล้ว แต่อยากอัปเดตโน้ตหรือจำนวนเพิ่มเข้าไปใหม่
        if parsed["count"] is not None or parsed["note"] is not None:
            existing.count = parsed["count"]
            existing.note = parsed["note"]
            await db.commit()
            return f"📝 อัปเดต {parsed['code']} {parsed['category']}"
        
        # ถ้าส่งมาแค่รหัสเพียวๆ ถึงจะเรียกว่าเป็นการสั่ง Toggle (ลบออก)
        await db.delete(existing)
        await db.commit()
        return f"↩️ ยกเลิก {parsed['code']} {parsed['category']}"

    entry = DiaryEntry(
        user_id=user_id,
        entry_date=today,
        code=parsed["code"],
        category=parsed["category"],
        done=True,
        count=parsed["count"],
        note=parsed["note"],
    )

    db.add(entry)
    await db.commit()

    symbol = get_symbol(today)
    return f"{symbol} {parsed['code']} {parsed['category']}"

# =========================================================
# Message Processor
# =========================================================

async def process_message(
    db: AsyncSession,
    user_id: str,
    text: str,
) -> str:
    text = text.strip()
    lower = text.lower()
    today = today_bkk()

    # Help
    if lower in HELP_CMDS:
        code_lines = "\n".join(
            f"{code} = {category}"
            for code, category in COMMAND_MAP.items()
        )
        return f"📋 Habit Codes\n\n{code_lines}\n\n~ข้อความ = บันทึก note\nsum = สรุปวันนี้"

    # Summary
    if lower in SUMMARY_CMDS:
        result = await db.execute(
            select(DiaryEntry).where(
                DiaryEntry.user_id == user_id,
                DiaryEntry.entry_date == today,
            )
        )
        entries = list(result.scalars().all())
        return build_summary(entries, today)

    # Free note
    if text.startswith("~"):
        note = text[1:].strip()

        if not note:
            return "❌ note ว่างเปล่า"

        if len(note) > NOTE_MAX_LEN:
            return f"❌ note ยาวเกิน {NOTE_MAX_LEN} ตัวอักษร"

        entry = DiaryEntry(
            user_id=user_id,
            entry_date=today,
            code=f"~~{uuid.uuid4().hex[:8]}",
            category="note",
            done=True,
            note=note,
        )

        db.add(entry)
        await db.commit()
        return f"📝 {note}"

    # Habit toggle
    parsed = parse_message(text)

    if parsed["type"] in ("invalid", "note"):
        return "❌ ไม่รู้จักคำสั่ง พิมพ์ help เพื่อดูรหัส"

    return await toggle_habit(db, user_id, parsed)

# =========================================================
# Routes
# =========================================================

VERSION = "1.0.0"


@app.get("/ping")
async def ping():
    return {
        "status": "ok",
        "version": VERSION,
        "time": datetime.now(BANGKOK).isoformat(),
        "tz": str(BANGKOK),
    }


@app.post("/callback")
async def callback(request: Request):
    body = await request.body()

    if is_duplicate(body):
        logger.info("Duplicate webhook ignored")
        return {"status": "duplicate"}

    signature = request.headers.get("X-Line-Signature", "")

    try:
        events = parser.parse(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=401, detail="invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue

        if not isinstance(event.message, TextMessageContent):
            continue

        user_id = getattr(event.source, "user_id", None)

        if not user_id:
            continue

        text = event.message.text.strip()

        async with SessionLocal() as db:
            try:
                response = await process_message(db, user_id, text)
            except Exception:
                logger.exception("process_message error")
                response = "❌ เกิดข้อผิดพลาด กรุณาลองใหม่"

        try:
            await reply_message(event.reply_token, response)
        except Exception:
            logger.exception("reply_message error")

    return {"status": "ok"}
