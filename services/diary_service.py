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

    # ดึง free note มาแถมต่อท้ายใน text summary ดั้งเดิม
    notes = [e.note for e in entries if e.code.startswith("~~") and e.note]
    if notes:
        lines.append("─" * 24)
        lines.append("📝 บันทึกวันนี้:")
        for idx, n in enumerate(notes, 1):
            lines.append(f"  {idx}. {n}")

    lines.append("─" * 24)
    lines.append(f"✅ {done_count}/{len(COMMAND_MAP)}")

    return "\n".join(lines)


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
