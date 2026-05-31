import re
import uuid
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DiaryEntry

logger = logging.getLogger(__name__)

# Timezone
BANGKOK = ZoneInfo("Asia/Bangkok")

# Constants
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

def today_bkk() -> date:
    return datetime.now(BANGKOK).date()


def get_symbol(target_date: date) -> str:
    return "●" if target_date.day % 2 == 0 else "■"


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


async def toggle_habit(
    db: AsyncSession,
    user_id: str,
    parsed: dict,
) -> dict:
    """สั่งเปิด-ปิดรหัสความสำเร็จ พร้อมคำนวณจำนวนที่เสร็จสิ้นประจำวันเพื่อคืนค่า Flex Confirmation"""
    today = today_bkk()

    stmt = select(DiaryEntry).where(
        DiaryEntry.user_id == user_id,
        DiaryEntry.entry_date == today,
        DiaryEntry.code == parsed["code"],
    )

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    is_done = True
    if existing:
        # ถ้ามีอยู่แล้ว แต่อยากอัปเดตโน้ตหรือจำนวนเพิ่มเข้าไปใหม่
        if parsed["count"] is not None or parsed["note"] is not None:
            existing.count = parsed["count"]
            existing.note = parsed["note"]
            await db.commit()
            logger.info(f"Updated habit {parsed['code']} with count={parsed['count']} note={parsed['note']} for user {user_id}")
        else:
            # ถ้าส่งมาแค่รหัสเพียวๆ ถึงจะเรียกว่าเป็นการสั่ง Toggle (ลบออก)
            await db.delete(existing)
            await db.commit()
            is_done = False
            logger.info(f"Toggled OFF habit {parsed['code']} for user {user_id}")
    else:
        # หากยังไม่มี ให้สร้างใหม่
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
        logger.info(f"Toggled ON habit {parsed['code']} for user {user_id}")

    # ดึงข้อมูลของวันนี้ทั้งหมดเพื่อสรุปความก้าวหน้าระหว่างวัน
    summary_stmt = select(DiaryEntry).where(
        DiaryEntry.user_id == user_id,
        DiaryEntry.entry_date == today,
    )
    summary_res = await db.execute(summary_stmt)
    entries = list(summary_res.scalars().all())

    # คำนวณเปอร์เซ็นต์
    done_count = sum(1 for e in entries if not e.code.startswith("~~") and e.done)
    total_habits = len(COMMAND_MAP)

    from flex.flex_builders import build_toggle_flex
    return build_toggle_flex(parsed["code"], parsed["category"], is_done, done_count, total_habits)


async def process_message(
    db: AsyncSession,
    user_id: str,
    text: str,
) -> str | dict:
    """แกนหลักประมวลผลวิเคราะห์ข้อความ คืนค่าเป็น Text (ข้อความปกติ) หรือ Dict (Flex Message JSON)"""
    text = text.strip()
    lower = text.lower()
    today = today_bkk()

    # Help Menu (Flex Grid 2 คอลัมน์)
    if lower in HELP_CMDS:
        from flex.flex_builders import build_help_flex
        return build_help_flex(COMMAND_MAP)

    # Summary Report (Flex Progress Bar + Reflections)
    if lower in SUMMARY_CMDS:
        result = await db.execute(
            select(DiaryEntry).where(
                DiaryEntry.user_id == user_id,
                DiaryEntry.entry_date == today,
            )
        )
        entries = list(result.scalars().all())
        from flex.flex_builders import build_summary_flex
        return build_summary_flex(entries, today, COMMAND_MAP)

    # Free note (Text)
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

    # Habit toggle (Flex Confirmation)
    parsed = parse_message(text)

    if parsed["type"] in ("invalid", "note"):
        return "❌ ไม่รู้จักคำสั่ง พิมพ์ help เพื่อดูรหัส"

    return await toggle_habit(db, user_id, parsed)
