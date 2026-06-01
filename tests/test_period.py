import unittest
import asyncio
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


class TestPeriodSummaryAggregation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Set up an in-memory SQLite database
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        self.Session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.Session()
        
        self.user_id = "U_TEST_USER"
        self.today = date(2026, 6, 1)
        self.command_map = {
            "99": "AI Coding",
            "77": "Mindfulness",
            "33": "PU @ 10",
        }

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_empty_period(self):
        # 1. ตรรกะกรณีไม่มีข้อมูลเลย
        start = self.today - timedelta(days=6) # 7-day period
        res = await get_period_summary(self.db, self.user_id, start, self.today, self.command_map)
        
        self.assertEqual(res["total_checkmarks"], 0)
        self.assertEqual(res["active_days"], 0)
        self.assertEqual(res["completion_rate"], 0)
        self.assertIsNone(res["top_habit_code"])
        self.assertEqual(res["top_habit_name"], "ไม่มี")
        self.assertEqual(res["current_streak"], 0)
        self.assertEqual(res["longest_streak"], 0)

    async def test_standard_7_day_period(self):
        # 2. ตรรกะกรณีบันทึกความสำเร็จทั่วไป
        start = self.today - timedelta(days=6)
        
        # Seed entries
        # - today: 99
        # - today - 1: 99, 77 (2 checkmarks)
        # - today - 2: 77
        # - today - 4: 33 (break at today - 3)
        # - notes (~~reflection) -> should be ignored!
        entries = [
            DiaryEntry(user_id=self.user_id, entry_date=self.today, code="99", category="AI Coding", done=True),
            DiaryEntry(user_id=self.user_id, entry_date=self.today - timedelta(days=1), code="99", category="AI Coding", done=True),
            DiaryEntry(user_id=self.user_id, entry_date=self.today - timedelta(days=1), code="77", category="Mindfulness", done=True),
            DiaryEntry(user_id=self.user_id, entry_date=self.today - timedelta(days=2), code="77", category="Mindfulness", done=True),
            DiaryEntry(user_id=self.user_id, entry_date=self.today - timedelta(days=4), code="33", category="PU @ 10", done=True),
            # Reflection note (~~note)
            DiaryEntry(user_id=self.user_id, entry_date=self.today, code="~~note1", category="note", done=True, note="Ignore me"),
        ]
        
        self.db.add_all(entries)
        await self.db.commit()
        
        res = await get_period_summary(self.db, self.user_id, start, self.today, self.command_map)
        
        # Assertions
        # Total checkmarks (excluding note): 99 (2), 77 (2), 33 (1) = 5
        self.assertEqual(res["total_checkmarks"], 5)
        # Active days: today, today-1, today-2, today-4 = 4 unique days
        self.assertEqual(res["active_days"], 4)
        self.assertEqual(res["total_days"], 7)
        # Completion rate: (4 / 7) * 100 = 57%
        self.assertEqual(res["completion_rate"], 57)
        # Top Habit is a tie between 99 and 77 (2 each)
        self.assertIn(res["top_habit_code"], ["99", "77"])
        self.assertEqual(res["top_habit_freq"], 2)
        # Streaks: active_days = [today, today-1, today-2, today-4]
        # Current streak: anchor is today, goes back to today-2 -> 3 days
        # Longest streak: 3 days
        self.assertEqual(res["current_streak"], 3)
        self.assertEqual(res["longest_streak"], 3)


if __name__ == "__main__":
    unittest.main()
