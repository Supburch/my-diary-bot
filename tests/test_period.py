import pytest
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base, DiaryEntry
from services.diary_service import get_period_summary


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def command_map():
    return {
        "99": "AI Coding",
        "77": "Mindfulness",
        "33": "PU @ 10",
    }


@pytest.fixture
def today():
    return date(2026, 6, 1)


@pytest.mark.asyncio
async def test_empty_period(db_session, command_map, today):
    start = today - timedelta(days=6)
    res = await get_period_summary(db_session, "U_TEST_USER", start, today, command_map)

    assert res["total_checkmarks"] == 0
    assert res["active_days"] == 0
    assert res["completion_rate"] == 0
    assert res["top_habit_code"] is None
    assert res["top_habit_name"] == "ไม่มี"
    assert res["current_streak"] == 0
    assert res["longest_streak"] == 0


@pytest.mark.asyncio
async def test_standard_7_day_period(db_session, command_map, today):
    start = today - timedelta(days=6)
    entries = [
        DiaryEntry(user_id="U_TEST_USER", entry_date=today, code="99", category="AI Coding", done=True),
        DiaryEntry(user_id="U_TEST_USER", entry_date=today - timedelta(days=1), code="99", category="AI Coding", done=True),
        DiaryEntry(user_id="U_TEST_USER", entry_date=today - timedelta(days=1), code="77", category="Mindfulness", done=True),
        DiaryEntry(user_id="U_TEST_USER", entry_date=today - timedelta(days=2), code="77", category="Mindfulness", done=True),
        DiaryEntry(user_id="U_TEST_USER", entry_date=today - timedelta(days=4), code="33", category="PU @ 10", done=True),
        DiaryEntry(user_id="U_TEST_USER", entry_date=today, code="~~note1", category="note", done=True, note="Ignore me"),
    ]
    db_session.add_all(entries)
    await db_session.commit()

    res = await get_period_summary(db_session, "U_TEST_USER", start, today, command_map)

    assert res["total_checkmarks"] == 5
    assert res["active_days"] == 4
    assert res["total_days"] == 7
    assert res["completion_rate"] == 57
    assert res["top_habit_code"] in ["99", "77"]
    assert res["top_habit_freq"] == 2
    assert res["current_streak"] == 3
    assert res["longest_streak"] == 3


@pytest.mark.asyncio
async def test_leap_year_period(db_session, command_map):
    leap_start = date(2024, 2, 28)
    leap_end = date(2024, 3, 1)
    entries = [
        DiaryEntry(user_id="U_TEST_USER", entry_date=date(2024, 2, 28), code="99", category="AI Coding", done=True),
        DiaryEntry(user_id="U_TEST_USER", entry_date=date(2024, 2, 29), code="99", category="AI Coding", done=True),
        DiaryEntry(user_id="U_TEST_USER", entry_date=date(2024, 3, 1), code="99", category="AI Coding", done=True),
    ]
    db_session.add_all(entries)
    await db_session.commit()

    res = await get_period_summary(db_session, "U_TEST_USER", leap_start, leap_end, command_map)

    assert res["total_checkmarks"] == 3
    assert res["active_days"] == 3
    assert res["total_days"] == 3
    assert res["completion_rate"] == 100
    assert res["current_streak"] == 3


@pytest.mark.asyncio
async def test_count_summation_period(db_session, command_map):
    count_start = date(2026, 7, 1)
    count_end = date(2026, 7, 3)
    entries = [
        DiaryEntry(user_id="U_TEST_USER", entry_date=date(2026, 7, 1), code="99", category="AI Coding", done=True, count=3),
        DiaryEntry(user_id="U_TEST_USER", entry_date=date(2026, 7, 2), code="99", category="AI Coding", done=True, count=2),
        DiaryEntry(user_id="U_TEST_USER", entry_date=date(2026, 7, 2), code="77", category="Mindfulness", done=True),
    ]
    db_session.add_all(entries)
    await db_session.commit()

    res = await get_period_summary(db_session, "U_TEST_USER", count_start, count_end, command_map)

    assert res["total_checkmarks"] == 6
    assert res["top_habit_code"] == "99"
    assert res["top_habit_freq"] == 5
