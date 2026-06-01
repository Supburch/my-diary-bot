import re
import uuid
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DiaryEntry

logger = logging.getLogger(__name__)

# Timezone
BANGKOK = ZoneInfo("Asia/Bangkok")

from config.user_habits import get_command_map

SUMMARY_CMDS = {"summary", "sum", "สรุป", "วันนี้", "รวม"}
HELP_CMDS = {"help", "รหัส", "code", "?", "เมนู"}
WEEKLY_CMDS = {"weekly", "สัปดาห์", "week"}
MONTHLY_CMDS = {"monthly", "เดือน", "month"}
NOTE_MAX_LEN = 500

def today_bkk() -> date:
    return datetime.now(BANGKOK).date()


def calculate_streak(active_dates: list[date], today: date) -> tuple[int, int]:
    """คำนวณหาสถิติการทำต่อเนื่อง (Current Streak) และประวัติทำต่อเนื่องยาวนานที่สุด (Best Streak)
    จากลิสต์ของวันที่บันทึกความสำเร็จ (เฉพาะ Habit ไม่รวม Note)
    """
    if not active_dates:
        return 0, 0
        
    # กรองเอาตัวซ้ำออกและเรียงลำดับจากเก่าไปใหม่
    unique_dates = sorted(list(set(active_dates)))
    
    # 1. คำนวณ Best Streak (ทำต่อเนื่องยาวนานที่สุด)
    best_streak = 0
    temp_streak = 0
    prev_date = None
    
    for d in unique_dates:
        if prev_date is None:
            temp_streak = 1
        else:
            diff = (d - prev_date).days
            if diff == 1:
                temp_streak += 1
            elif diff > 1:
                if temp_streak > best_streak:
                    best_streak = temp_streak
                temp_streak = 1
        prev_date = d
        
    if temp_streak > best_streak:
        best_streak = temp_streak
        
    # 2. คำนวณ Current Streak (ทำต่อเนื่องปัจจุบัน)
    active_set = set(unique_dates)
    anchor = None
    
    if today in active_set:
        anchor = today
    elif (today - timedelta(days=1)) in active_set:
        anchor = today - timedelta(days=1)
        
    current_streak = 0
    if anchor is not None:
        cursor = anchor
        while cursor in active_set:
            current_streak += 1
            cursor -= timedelta(days=1)
            
    return current_streak, best_streak


async def get_user_streaks(db: AsyncSession, user_id: str, today: date) -> tuple[int, int]:
    """ดึงข้อมูลประวัติวันที่สำเร็จของ user_id เพื่อส่งกลับผลลัพธ์คำนวณ Streak (เฉพาะ Habit ไม่รวม Note)"""
    stmt = select(DiaryEntry.entry_date).where(
        DiaryEntry.user_id == user_id,
        DiaryEntry.done == True,
        ~DiaryEntry.code.like("~~%")
    )
    result = await db.execute(stmt)
    dates = list(result.scalars().all())
    return calculate_streak(dates, today)


async def get_period_summary(
    db: AsyncSession,
    user_id: str,
    start_date: date,
    end_date: date,
    command_map: dict[str, str]
) -> dict:
    """ประมวลผลสรุปประวัติความก้าวหน้าข้ามช่วงเวลา (เช่น รายสัปดาห์ หรือรายเดือน)
    ดึงข้อมูลทั้งหมดเฉพาะ Habit ที่ไม่ซ้ำ และคำนวณสถิติ เช็คลิสต์ อัตราความสำเร็จ และ Top Habit
    """
    from collections import Counter
    stmt = select(DiaryEntry).where(
        DiaryEntry.user_id == user_id,
        DiaryEntry.entry_date >= start_date,
        DiaryEntry.entry_date <= end_date,
        DiaryEntry.done == True,
        ~DiaryEntry.code.like("~~%")
    )
    result = await db.execute(stmt)
    entries = list(result.scalars().all())

    total_checkmarks = len(entries)
    total_days = (end_date - start_date).days + 1
    unique_active_dates = {e.entry_date for e in entries}
    active_days_count = len(unique_active_dates)
    completion_rate = int((active_days_count / total_days) * 100) if total_days > 0 else 0
    
    habit_codes = [e.code for e in entries if e.code in command_map]
    if habit_codes:
        counter = Counter(habit_codes)
        top_code, top_freq = counter.most_common(1)[0]
        top_habit_name = command_map.get(top_code, top_code)
    else:
        top_code, top_freq, top_habit_name = None, 0, "ไม่มี"

    current_streak, longest_streak = calculate_streak(list(unique_active_dates), end_date)

    return {
        "total_checkmarks": total_checkmarks,
        "active_days": active_days_count,
        "total_days": total_days,
        "completion_rate": completion_rate,
        "top_habit_code": top_code,
        "top_habit_freq": top_freq,
        "top_habit_name": top_habit_name,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
    }


def get_symbol(target_date: date) -> str:
    return "●" if target_date.day % 2 == 0 else "■"


def parse_message(text: str, command_map: dict[str, str]) -> dict:
    text = text.strip()

    if not text:
        return {"type": "invalid"}

    parts = text.split(maxsplit=2)
    code = parts[0]

    if not re.fullmatch(r"\d{2}", code):
        return {"type": "note", "note": text}

    category = command_map.get(code)

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
    command_map: dict[str, str],
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
    total_habits = len(command_map)

    # คำนวณ Streak ปัจจุบัน
    current_streak, _ = await get_user_streaks(db, user_id, today)

    from flex.flex_builders import build_toggle_flex
    return build_toggle_flex(
        parsed["code"],
        parsed["category"],
        is_done,
        done_count,
        total_habits,
        current_streak=current_streak,
    )


async def process_message(
    db: AsyncSession,
    user_id: str,
    text: str,
) -> str | dict:
    """แกนหลักประมวลผลวิเคราะห์ข้อความ คืนค่าเป็น Text (ข้อความปกติ) หรือ Dict (Flex Message JSON)"""
    text = text.strip()
    lower = text.lower()
    today = today_bkk()
    command_map = get_command_map(user_id)

    # Weekly & Monthly Summary reports
    if lower in WEEKLY_CMDS:
        start_date = today - timedelta(days=6)
        stats = await get_period_summary(db, user_id, start_date, today, command_map)
        from flex.flex_builders import build_period_summary_flex
        return build_period_summary_flex("Weekly Summary", start_date, today, stats)

    if lower in MONTHLY_CMDS:
        start_date = today - timedelta(days=29)
        stats = await get_period_summary(db, user_id, start_date, today, command_map)
        from flex.flex_builders import build_period_summary_flex
        return build_period_summary_flex("Monthly Summary", start_date, today, stats)

    # Help Menu (Flex Grid 2 คอลัมน์)
    if lower in HELP_CMDS:
        from flex.flex_builders import build_help_flex
        return build_help_flex(command_map)

    # Summary Report (Flex Progress Bar + Reflections)
    if lower in SUMMARY_CMDS:
        result = await db.execute(
            select(DiaryEntry).where(
                DiaryEntry.user_id == user_id,
                DiaryEntry.entry_date == today,
            )
        )
        entries = list(result.scalars().all())
        
        # คำนวณความต่อเนื่อง (Streak)
        current_streak, best_streak = await get_user_streaks(db, user_id, today)
        
        from flex.flex_builders import build_summary_flex
        return build_summary_flex(
            entries,
            today,
            command_map,
            current_streak=current_streak,
            best_streak=best_streak
        )

    # Free note (Text)
    if text.startswith("***"):
        note = text[3:].strip()

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
    parsed = parse_message(text, command_map)

    if parsed["type"] in ("invalid", "note"):
        return "❌ ไม่รู้จักคำสั่ง โปรดพิมพ์ help หรือ เมนู เพื่อออกคำสั่งต่อไป"

    return await toggle_habit(db, user_id, parsed, command_map)
