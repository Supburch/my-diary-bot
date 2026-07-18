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

from config.user_habits import get_command_map, get_habit_icons

SUMMARY_CMDS = {"summary", "sum", "สรุป", "วันนี้", "รวม"}
HELP_CMDS = {"help", "รหัส", "code", "?", "เมนู"}
GUIDE_CMDS = {"guide", "คู่มือ", "วิธีใช้"}
WEEKLY_CMDS = {"weekly", "สัปดาห์", "week"}
MONTHLY_CMDS = {"monthly", "เดือน", "month"}
NOTE_SUMMARY_PREFIXES = {"สรุปโน้ต", "note", "โน้ต"}
NOTE_MAX_LEN = 500

# ชื่อเดือนภาษาไทย
THAI_MONTHS = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม",
}

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


async def get_notes_by_period(
    db: AsyncSession,
    user_id: str,
    start_date: date,
    end_date: date,
) -> list:
    """ดึงโน้ตทั้งหมดของผู้ใช้ในช่วงเวลาที่กำหนด (entries ที่ code ขึ้นต้นด้วย ~~)"""
    stmt = select(DiaryEntry).where(
        DiaryEntry.user_id == user_id,
        DiaryEntry.entry_date >= start_date,
        DiaryEntry.entry_date <= end_date,
        DiaryEntry.code.like("~~%")
    ).order_by(DiaryEntry.entry_date.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


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

    total_checkmarks = sum(e.count if (e.count is not None and e.count > 0) else 1 for e in entries)
    total_days = (end_date - start_date).days + 1
    unique_active_dates = {e.entry_date for e in entries}
    active_days_count = len(unique_active_dates)
    completion_rate = int((active_days_count / total_days) * 100) if total_days > 0 else 0
    
    if entries:
        counter = Counter()
        for e in entries:
            if e.code in command_map:
                counter[e.code] += e.count if (e.count is not None and e.count > 0) else 1
        if counter:
            top_code, top_freq = counter.most_common(1)[0]
            top_habit_name = command_map.get(top_code, top_code)
        else:
            top_code, top_freq, top_habit_name = None, 0, "ไม่มี"
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

    # ค้นหาและสกัดปี ค.ศ. (4 หลัก เช่น 1990-2099) เพื่อใช้บันทึกข้อมูลย้อนหลังแยกเป็นปี
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    target_year = None
    if year_match:
        target_year = int(year_match.group(1))
        # ลบปีออกจากข้อความเพื่อป้องกันการนำไป parse สับสนกับ count
        text = text.replace(year_match.group(1), "").strip()
        text = re.sub(r"\s+", " ", text)

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
        "year": target_year,
    }


async def toggle_habit(
    db: AsyncSession,
    user_id: str,
    parsed: dict,
    command_map: dict[str, str],
) -> dict:
    """สั่งเปิด-ปิดรหัสความสำเร็จ พร้อมคำนวณจำนวนที่เสร็จสิ้นประจำวันเพื่อคืนค่า Flex Confirmation"""
    today = today_bkk()
    entry_date = today
    if parsed.get("year"):
        try:
            entry_date = date(parsed["year"], today.month, today.day)
        except ValueError:
            # รับมือกรณีวันที่ 29 ก.พ. ในปีที่ไม่ใช่อธิกสุรทิน
            entry_date = date(parsed["year"], today.month, 28)

    stmt = select(DiaryEntry).where(
        DiaryEntry.user_id == user_id,
        DiaryEntry.entry_date == entry_date,
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
            logger.info(f"Updated habit {parsed['code']} with count={parsed['count']} note={parsed['note']} for user {user_id} on {entry_date}")
        else:
            # ถ้าส่งมาแค่รหัสเพียวๆ ถึงจะเรียกว่าเป็นการสั่ง Toggle (ลบออก)
            await db.delete(existing)
            await db.commit()
            is_done = False
            logger.info(f"Toggled OFF habit {parsed['code']} for user {user_id} on {entry_date}")
    else:
        # หากยังไม่มี ให้สร้างใหม่
        entry = DiaryEntry(
            user_id=user_id,
            entry_date=entry_date,
            code=parsed["code"],
            category=parsed["category"],
            done=True,
            count=parsed["count"],
            note=parsed["note"],
        )
        db.add(entry)
        await db.commit()
        logger.info(f"Toggled ON habit {parsed['code']} for user {user_id} on {entry_date}")

    # ดึงข้อมูลของวันนั้นๆ ทั้งหมดเพื่อสรุปความก้าวหน้าระหว่างวัน
    summary_stmt = select(DiaryEntry).where(
        DiaryEntry.user_id == user_id,
        DiaryEntry.entry_date == entry_date,
    )
    summary_res = await db.execute(summary_stmt)
    entries = list(summary_res.scalars().all())

    # คำนวณเปอร์เซ็นต์ (รวมจำนวนครั้งจริงจาก count field)
    done_count = sum(
        (e.count if (e.count is not None and e.count > 0) else 1)
        for e in entries
        if not e.code.startswith("~~") and e.done
    )
    total_habits = len(command_map)

    # คำนวณ Streak ปัจจุบัน (ยึดตามวันจริงของ today)
    current_streak, _ = await get_user_streaks(db, user_id, today)

    from flex.flex_builders import build_toggle_flex
    return build_toggle_flex(
        parsed["code"],
        parsed["category"],
        is_done,
        done_count,
        total_habits,
        command_map,
        current_streak=current_streak,
        count=parsed["count"],
        note=parsed["note"],
    )


def parse_note_summary_command(text: str) -> dict | None:
    """Parse คำสั่งสรุปโน้ต เช่น 'สรุปโน้ต 01', 'note 2024', 'สรุปโน้ต'
    คืนค่า dict ที่มี period_type ('month'/'year') และ value (int)
    หากไม่ใช่คำสั่งสรุปโน้ตให้คืน None
    """
    lower = text.strip().lower()
    matched_prefix = None
    for prefix in NOTE_SUMMARY_PREFIXES:
        if lower.startswith(prefix):
            matched_prefix = prefix
            break
    if matched_prefix is None:
        return None

    remainder = lower[len(matched_prefix):].strip()

    # ไม่มีตัวเลขตามหลัง → ดูโน้ตเดือนปัจจุบัน
    if not remainder:
        return {"period_type": "current_month"}

    # ตัวเลข 1–2 หลัก (01–12) → ดูรายเดือน
    month_match = re.fullmatch(r"0?(\d{1,2})", remainder)
    if month_match:
        month_val = int(month_match.group(1))
        if 1 <= month_val <= 12:
            return {"period_type": "month", "value": month_val}

    # ตัวเลข 4 หลัก (เช่น 2024) → ดูรายปี
    year_match = re.fullmatch(r"(19\d{2}|20\d{2})", remainder)
    if year_match:
        return {"period_type": "year", "value": int(year_match.group(1))}

    return None


def parse_infographic_command(text: str) -> dict | None:
    """Parse คำสั่งสรุปภาพ เช่น 'สรุปภาพ 01', 'stats 2024', 'สรุปภาพ'
    คืนค่า dict ที่มี period_type ('month'/'year'/'current_month') และ value (int | None)
    หากไม่ใช่คำสั่งสรุปภาพให้คืน None
    """
    lower = text.strip().lower()
    INFOGRAPHIC_PREFIXES = {"สรุปภาพ", "สรุปรูป", "stats", "stat", "ig", "ภาพสรุป", "รูปสรุป"}
    matched_prefix = None
    for prefix in sorted(INFOGRAPHIC_PREFIXES, key=len, reverse=True):
        if lower.startswith(prefix):
            matched_prefix = prefix
            break
    if matched_prefix is None:
        return None

    remainder = lower[len(matched_prefix):].strip()

    # ไม่มีตัวระบุตามหลัง -> ดูสถิติเดือนปัจจุบัน
    if not remainder:
        return {"period_type": "current_month"}

    # ตัวเลข 1–2 หลัก (01–12) -> ดูรายเดือน
    month_match = re.fullmatch(r"0?(\d{1,2})", remainder)
    if month_match:
        month_val = int(month_match.group(1))
        if 1 <= month_val <= 12:
            return {"period_type": "month", "value": month_val}

    # ตัวเลข 4 หลัก (เช่น 2024) -> ดูรายปี
    year_match = re.fullmatch(r"(19\d{2}|20\d{2})", remainder)
    if year_match:
        return {"period_type": "year", "value": int(year_match.group(1))}

    return None


async def process_message(
    db: AsyncSession,
    user_id: str,
    text: str,
) -> str | dict:
    """แกนหลักประมวลผลวิเคราะห์ข้อความ คืนค่าเป็น Text (ข้อความปกติ) หรือ Dict (Flex Message JSON)"""
    text = text.strip()
    lower = text.lower()
    today = today_bkk()
    command_map = await get_command_map(db, user_id)
    custom_icons = await get_habit_icons(db, user_id)

    # Dynamic Habit Management
    if lower.startswith("เพิ่ม "):
        parts = text.split(maxsplit=3)
        if len(parts) >= 3:
            code = parts[1]
            if code.isdigit() and len(code) == 2:
                name = parts[2]
                icon = parts[3] if len(parts) == 4 else "▪"
                
                from db.models import UserHabit
                
                existing = await db.execute(select(UserHabit).where(UserHabit.user_id == user_id, UserHabit.code == code))
                habit = existing.scalar_one_or_none()
                
                if habit:
                    habit.category = name
                    habit.icon = icon
                else:
                    habit = UserHabit(user_id=user_id, code=code, category=name, icon=icon)
                    db.add(habit)
                    
                await db.commit()
                return f"✅ บันทึกกิจกรรมใหม่สำเร็จ!\nรหัส: {code}\nชื่อ: {name}\nไอคอน: {icon}"
            else:
                return "❌ รหัสกิจกรรมต้องเป็นตัวเลข 2 หลักเท่านั้น เช่น 'เพิ่ม 12 วิ่ง 🏃'"
        else:
            return "❌ รูปแบบคำสั่งไม่ถูกต้อง\nวิธีใช้: เพิ่ม [รหัส2หลัก] [ชื่อ] [ไอคอน]\nตัวอย่าง: เพิ่ม 12 วิ่ง 🏃"

    if lower.startswith("ลบกิจกรรม ") or lower.startswith("ลบ "):
        parts = text.split()
        if len(parts) == 2:
            code = parts[1]
            if code.isdigit() and len(code) == 2:
                from db.models import UserHabit
                existing = await db.execute(select(UserHabit).where(UserHabit.user_id == user_id, UserHabit.code == code))
                habit = existing.scalar_one_or_none()
                if habit:
                    await db.delete(habit)
                    await db.commit()
                    return f"🗑️ ลบกิจกรรมรหัส {code} เรียบร้อยแล้ว"
                else:
                    return f"❌ ไม่พบกิจกรรมรหัส {code} ในระบบของคุณ"
            else:
                return "❌ รหัสกิจกรรมต้องเป็นตัวเลข 2 หลักเท่านั้น"

    # Note Summary (สรุปโน้ต)
    note_cmd = parse_note_summary_command(text)
    if note_cmd is not None:
        import calendar
        if note_cmd["period_type"] == "current_month":
            start_date = date(today.year, today.month, 1)
            end_date = today
            period_label = f"📝 โน้ตเดือน{THAI_MONTHS[today.month]} {today.year}"
        elif note_cmd["period_type"] == "month":
            m = note_cmd["value"]
            y = today.year
            start_date = date(y, m, 1)
            last_day = calendar.monthrange(y, m)[1]
            end_date = date(y, m, last_day)
            period_label = f"📝 โน้ตเดือน{THAI_MONTHS[m]} {y}"
        else:  # year
            y = note_cmd["value"]
            start_date = date(y, 1, 1)
            end_date = date(y, 12, 31)
            period_label = f"📝 โน้ตปี {y}"

        notes = await get_notes_by_period(db, user_id, start_date, end_date)
        from flex.flex_builders import build_note_summary_flex
        return build_note_summary_flex(period_label, notes, command_map, custom_icons)

    # Infographic Summary (สรุปภาพสถิติ)
    info_cmd = parse_infographic_command(text)
    if info_cmd is not None:
        import calendar
        if info_cmd["period_type"] == "current_month":
            start_date = date(today.year, today.month, 1)
            end_date = today
            period_label = f"สถิตินิสัยเดือน{THAI_MONTHS[today.month]} {today.year}"
        elif info_cmd["period_type"] == "month":
            m = info_cmd["value"]
            y = today.year
            start_date = date(y, m, 1)
            last_day = calendar.monthrange(y, m)[1]
            end_date = date(y, m, last_day)
            period_label = f"สถิตินิสัยเดือน{THAI_MONTHS[m]} {y}"
        else:  # year
            y = info_cmd["value"]
            start_date = date(y, 1, 1)
            end_date = date(y, 12, 31)
            period_label = f"สถิตินิสัยประจำปี {y}"

        # 1. Query ข้อมูลบันทึกความสำเร็จสำหรับช่วงเวลา
        stmt = select(DiaryEntry).where(
            DiaryEntry.user_id == user_id,
            DiaryEntry.entry_date >= start_date,
            DiaryEntry.entry_date <= end_date,
            DiaryEntry.done == True,
            ~DiaryEntry.code.like("~~%")
        )
        result = await db.execute(stmt)
        entries = list(result.scalars().all())

        # 2. คำนวณ Streaks ของผู้ใช้งาน
        current_streak, longest_streak = await get_user_streaks(db, user_id, today)

        # 3. คำนวณค่าสถิติทั่วไป
        total_checkmarks = sum(e.count if (e.count is not None and e.count > 0) else 1 for e in entries)
        total_days = (end_date - start_date).days + 1
        unique_active_dates = {e.entry_date for e in entries}
        active_days_count = len(unique_active_dates)
        completion_rate = int((active_days_count / total_days) * 100) if total_days > 0 else 0

        # หานิสัยยอดฮิตประจำตัว
        from collections import Counter
        if entries:
            counter = Counter()
            for e in entries:
                if e.code in command_map:
                    counter[e.code] += e.count if (e.count is not None and e.count > 0) else 1
            if counter:
                top_code, top_freq = counter.most_common(1)[0]
                top_habit_name = command_map.get(top_code, top_code)
            else:
                top_code, top_freq, top_habit_name = None, 0, "ไม่มี"
        else:
            top_code, top_freq, top_habit_name = None, 0, "ไม่มี"

        stats = {
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

        # 4. คำนวณสถิติรายข้อ (Habit Breakdown)
        habit_breakdown = []
        for code, name in command_map.items():
            count = sum(e.count if (e.count is not None and e.count > 0) else 1 for e in entries if e.code == code)
            pct = int((count / total_days) * 100) if total_days > 0 else 0
            habit_breakdown.append({
                "code": code,
                "name": name,
                "count": count,
                "pct": pct
            })
        # เรียงตามความถี่สูงสุด
        habit_breakdown.sort(key=lambda x: x["count"], reverse=True)

        # 5. สรุปความถี่รายวันสำหรับทำตาราง Contribution Calendar
        contribution_data = Counter()
        for e in entries:
            contribution_data[e.entry_date] += e.count if (e.count is not None and e.count > 0) else 1

        # กำหนดคีย์ระบุช่วงเวลาให้เป็นชื่อไฟล์แบบคงที่ (Static) เพื่อป้องกันไฟล์สะสมล้น Supabase
        if info_cmd["period_type"] == "current_month":
            period_key = f"monthly_{today.year}_{today.month:02d}"
        elif info_cmd["period_type"] == "month":
            period_key = f"monthly_{today.year}_{info_cmd['value']:02d}"
        else:
            period_key = f"yearly_{info_cmd['value']}"

        # 6. เรียกใช้ระบบทำอินโฟกราฟิกและอัปโหลดขึ้น Supabase Storage
        from services.infographic_service import generate_and_upload_infographic
        img_url = await generate_and_upload_infographic(
            user_id=user_id,
            period_label=period_label,
            period_key=period_key,
            stats=stats,
            habit_breakdown=habit_breakdown,
            contribution_data=contribution_data,
            start_date=start_date,
            end_date=end_date
        )

        if img_url:
            return {
                "type": "image",
                "original_content_url": img_url,
                "preview_image_url": img_url
            }
        else:
            # Fallback หากระบบจัดเก็บรูปภาพขัดข้อง ให้ทำรายงานเป็นข้อความตัวหนังสือให้อ่านแทน
            fallback_text = (
                f"❌ ไม่สามารถสร้างรูปภาพอินโฟกราฟิกได้ในขณะนี้ (อาจเนื่องจากไม่ได้ตั้งค่าคีย์ Supabase Storage ใน Render)\n\n"
                f"📊 ข้อมูลสถิตินิสัย ({period_label}):\n"
                f"• อัตราสำเร็จ: {completion_rate}%\n"
                f"• บันทึก {active_days_count}/{total_days} วัน\n"
                f"• จำนวนรวม: {total_checkmarks} ครั้ง\n"
                f"• ต่อเนื่องปัจจุบัน: {current_streak} วัน 🔥\n"
                f"• ดีที่สุด: {longest_streak} วัน 🏆\n"
                f"• นิสัยยอดฮิต: {top_habit_name} ({top_freq} ครั้ง)\n"
            )
            return fallback_text

    # Weekly & Monthly Summary reports
    if lower in WEEKLY_CMDS:
        start_date = today - timedelta(days=6)
        stats = await get_period_summary(db, user_id, start_date, today, command_map)
        from flex.flex_builders import build_period_summary_flex
        return build_period_summary_flex("Weekly Summary", start_date, today, stats, command_map, custom_icons)

    if lower in MONTHLY_CMDS:
        start_date = today - timedelta(days=29)
        stats = await get_period_summary(db, user_id, start_date, today, command_map)
        from flex.flex_builders import build_period_summary_flex
        return build_period_summary_flex("Monthly Summary", start_date, today, stats, command_map, custom_icons)

    # Help Menu (Flex Grid 2 คอลัมน์)
    if lower in HELP_CMDS:
        from flex.flex_builders import build_help_flex
        return build_help_flex(command_map, custom_icons)

    # Guide (User Guide ละเอียด)
    if lower in GUIDE_CMDS:
        from flex.flex_builders import build_guide_flex
        return build_guide_flex(command_map, custom_icons)

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
            best_streak=best_streak,
            custom_icons=custom_icons
        )

    # Free note (Text)
    if text.startswith("***"):
        note = text[3:].strip()
        # ค้นหาและสกัดปี ค.ศ. (4 หลัก เช่น 1990-2099) เพื่อใช้บันทึกโน้ตย้อนหลัง
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", note)
        note_date = today
        if year_match:
            parsed_year = int(year_match.group(1))
            try:
                note_date = date(parsed_year, today.month, today.day)
            except ValueError:
                # รับมือกรณีปีอธิกสุรทิน
                note_date = date(parsed_year, today.month, 28)
            # ลบปีออกจากโน้ตเพื่อความสะอาด
            note = note.replace(year_match.group(1), "").strip()
            note = re.sub(r"\s+", " ", note)

        if not note:
            return "❌ note ว่างเปล่า"

        if len(note) > NOTE_MAX_LEN:
            return f"❌ note ยาวเกิน {NOTE_MAX_LEN} ตัวอักษร"

        entry = DiaryEntry(
            user_id=user_id,
            entry_date=note_date,
            code=f"~~{uuid.uuid4().hex[:8]}",
            category="note",
            done=True,
            note=note,
        )

        db.add(entry)
        await db.commit()
        return f"📝 {note} (ปี {note_date.year})" if note_date.year != today.year else f"📝 {note}"

    # Habit toggle (Flex Confirmation)
    parsed = parse_message(text, command_map)

    if parsed["type"] in ("invalid", "note"):
        return "❌ ไม่รู้จักคำสั่ง โปรดพิมพ์ help หรือ เมนู เพื่อออกคำสั่งต่อไป"

    return await toggle_habit(db, user_id, parsed, command_map)
