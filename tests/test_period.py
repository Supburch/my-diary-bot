from datetime import date, timedelta
from collections import Counter
from sqlalchemy import select, Boolean, Date, Integer, String, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Declarative base for testing
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


# The O(N) Streak calculation logic
def calculate_streak(active_dates: list[date], today: date) -> tuple[int, int]:
    if not active_dates:
        return 0, 0
    unique_dates = sorted(list(set(active_dates)))
    
    # 1. Best Streak
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
        
    # 2. Current Streak
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


# The period summary logic under test
async def get_period_summary(
    db: AsyncSession,
    user_id: str,
    start_date: date,
    end_date: date,
    command_map: dict[str, str]
) -> dict:
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


async def run_period_tests() -> dict:
    """สั่งรันชุดทดสอบความถูกต้องของระบบสรุปรายงานข้ามช่วงเวลาแบบอะซิงโครนัสใน event loop เดียวกัน"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    db = Session()
    
    user_id = "U_TEST_USER"
    today = date(2026, 6, 1)
    command_map = {
        "99": "AI Coding",
        "77": "Mindfulness",
        "33": "PU @ 10",
    }
    
    output_lines = []
    
    try:
        # Case 1: Empty period
        start = today - timedelta(days=6)
        res = await get_period_summary(db, user_id, start, today, command_map)
        
        assert res["total_checkmarks"] == 0, f"Expected 0 checkmarks, got {res['total_checkmarks']}"
        assert res["active_days"] == 0
        assert res["completion_rate"] == 0
        assert res["top_habit_code"] is None
        assert res["top_habit_name"] == "ไม่มี"
        assert res["current_streak"] == 0
        assert res["longest_streak"] == 0
        output_lines.append("test_empty_period ... PASS")
        
        # Case 2: Standard 7-day period
        entries = [
            DiaryEntry(user_id=user_id, entry_date=today, code="99", category="AI Coding", done=True),
            DiaryEntry(user_id=user_id, entry_date=today - timedelta(days=1), code="99", category="AI Coding", done=True),
            DiaryEntry(user_id=user_id, entry_date=today - timedelta(days=1), code="77", category="Mindfulness", done=True),
            DiaryEntry(user_id=user_id, entry_date=today - timedelta(days=2), code="77", category="Mindfulness", done=True),
            DiaryEntry(user_id=user_id, entry_date=today - timedelta(days=4), code="33", category="PU @ 10", done=True),
            # Reflection note (~~note)
            DiaryEntry(user_id=user_id, entry_date=today, code="~~note1", category="note", done=True, note="Ignore me"),
        ]
        
        db.add_all(entries)
        await db.commit()
        
        res = await get_period_summary(db, user_id, start, today, command_map)
        
        assert res["total_checkmarks"] == 5, f"Expected 5 checkmarks, got {res['total_checkmarks']}"
        assert res["active_days"] == 4
        assert res["total_days"] == 7
        assert res["completion_rate"] == 57, f"Expected 57% completion rate, got {res['completion_rate']}"
        assert res["top_habit_code"] in ["99", "77"]
        assert res["top_habit_freq"] == 2
        assert res["current_streak"] == 3, f"Expected current streak 3, got {res['current_streak']}"
        assert res["longest_streak"] == 3
        output_lines.append("test_standard_7_day_period ... PASS")
        
        # Case 3: Leap Year (2024-02-29)
        leap_start = date(2024, 2, 28)
        leap_end = date(2024, 3, 1)
        leap_entries = [
            DiaryEntry(user_id=user_id, entry_date=date(2024, 2, 28), code="99", category="AI Coding", done=True),
            DiaryEntry(user_id=user_id, entry_date=date(2024, 2, 29), code="99", category="AI Coding", done=True), # Leap Day!
            DiaryEntry(user_id=user_id, entry_date=date(2024, 3, 1), code="99", category="AI Coding", done=True),
        ]
        db.add_all(leap_entries)
        await db.commit()
        
        leap_res = await get_period_summary(db, user_id, leap_start, leap_end, command_map)
        assert leap_res["total_checkmarks"] == 3, f"Expected 3 checkmarks, got {leap_res['total_checkmarks']}"
        assert leap_res["active_days"] == 3
        assert leap_res["total_days"] == 3
        assert leap_res["completion_rate"] == 100
        assert leap_res["current_streak"] == 3
        output_lines.append("test_leap_year_period ... PASS")

        # Case 4: Habit count summation verification
        count_start = date(2026, 7, 1)
        count_end = date(2026, 7, 3)
        count_entries = [
            DiaryEntry(user_id=user_id, entry_date=date(2026, 7, 1), code="99", category="AI Coding", done=True, count=3),
            DiaryEntry(user_id=user_id, entry_date=date(2026, 7, 2), code="99", category="AI Coding", done=True, count=2),
            DiaryEntry(user_id=user_id, entry_date=date(2026, 7, 2), code="77", category="Mindfulness", done=True), # count is None (defaults to 1)
        ]
        db.add_all(count_entries)
        await db.commit()
        
        count_res = await get_period_summary(db, user_id, count_start, count_end, command_map)
        # 3 + 2 + 1 = 6 checkmarks
        assert count_res["total_checkmarks"] == 6, f"Expected 6 checkmarks, got {count_res['total_checkmarks']}"
        # top habit should be 99 with freq 3 + 2 = 5
        assert count_res["top_habit_code"] == "99"
        assert count_res["top_habit_freq"] == 5, f"Expected frequency 5, got {count_res['top_habit_freq']}"
        output_lines.append("test_count_summation_period ... PASS")
        
        return {
            "status": "ok",
            "message": "All period summary unit tests passed successfully!",
            "output": "\n".join(output_lines)
        }
    except Exception as e:
        import traceback
        return {
            "status": "failed",
            "message": f"Test failed with error: {str(e)}",
            "traceback": traceback.format_exc()
        }
    finally:
        await db.close()
        await engine.dispose()
