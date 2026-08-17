"""Unit Tests สำหรับฟีเจอร์โน้ตด้วยคีย์เวิร์ด (บันทึก + เรียกกลับดู)"""
import pytest
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base, DiaryEntry
from services.diary_service import (
    split_keyword_note,
    parse_keyword_recall,
    get_notes_by_keyword,
)


class TestSplitKeywordNote:
    """ทดสอบการแยกคีย์เวิร์ดออกจากโน้ต (***keyword: เนื้อหา)"""

    def test_keyword_with_colon(self):
        assert split_keyword_note("wifi: รหัส 1234") == ("wifi", "รหัส 1234")

    def test_keyword_no_space_after_colon(self):
        assert split_keyword_note("wifi:รหัส") == ("wifi", "รหัส")

    def test_no_colon_is_normal_note(self):
        assert split_keyword_note("บันทึกทั่วไป") == (None, "บันทึกทั่วไป")

    def test_colon_with_space_in_keyword_is_normal(self):
        # "เวลา 15:30" ไม่ควรเป็นคีย์เวิร์ด (คีย์เวิร์ดต้องเป็นคำเดียว)
        assert split_keyword_note("เวลา 15:30 นัดหมอ") == (None, "เวลา 15:30 นัดหมอ")

    def test_empty_keyword_is_normal(self):
        assert split_keyword_note(": เนื้อหา") == (None, ": เนื้อหา")

    def test_empty_content_is_normal(self):
        assert split_keyword_note("wifi:") == (None, "wifi:")

    def test_keyword_strips_hash(self):
        assert split_keyword_note("#wifi: รหัส") == ("wifi", "รหัส")


class TestParseKeywordRecall:
    """ทดสอบการ parse คำสั่งเรียกดูโน้ตด้วยคีย์เวิร์ด"""

    def test_explicit_prefix_du(self):
        assert parse_keyword_recall("ดู wifi") == {"keyword": "wifi", "explicit": True}

    def test_explicit_prefix_ha(self):
        assert parse_keyword_recall("หา รหัส") == {"keyword": "รหัส", "explicit": True}

    def test_explicit_prefix_khon(self):
        assert parse_keyword_recall("ค้น ที่จอดรถ") == {"keyword": "ที่จอดรถ", "explicit": True}

    def test_hash_prefix(self):
        assert parse_keyword_recall("#wifi") == {"keyword": "wifi", "explicit": True}

    def test_bare_keyword(self):
        assert parse_keyword_recall("wifi") == {"keyword": "wifi", "explicit": False}

    def test_bare_keyword_case_insensitive(self):
        assert parse_keyword_recall("WiFi") == {"keyword": "wifi", "explicit": False}

    def test_two_digit_code_is_not_keyword(self):
        assert parse_keyword_recall("99") is None

    def test_empty(self):
        assert parse_keyword_recall("") is None

    def test_prefix_only(self):
        assert parse_keyword_recall("ดู") is None


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_notes_by_keyword(db_session):
    today = date(2026, 6, 1)
    db_session.add_all([
        DiaryEntry(user_id="U_TEST", entry_date=today, code="~~a", category="note", done=True, note="รหัส wifi", keyword="wifi"),
        DiaryEntry(user_id="U_TEST", entry_date=today, code="~~b", category="note", done=True, note="รหัส wifi สำรอง", keyword="wifi"),
        DiaryEntry(user_id="U_TEST", entry_date=today, code="~~c", category="note", done=True, note="รหัสบ้าน", keyword="บ้าน"),
        DiaryEntry(user_id="U_TEST", entry_date=today, code="~~d", category="note", done=True, note="โน้ตไม่มีคีย์เวิร์ด", keyword=None),
    ])
    await db_session.commit()

    wifi_notes = await get_notes_by_keyword(db_session, "U_TEST", "wifi")
    assert len(wifi_notes) == 2

    # case-insensitive
    wifi_notes_upper = await get_notes_by_keyword(db_session, "U_TEST", "WIFI")
    assert len(wifi_notes_upper) == 2

    home_notes = await get_notes_by_keyword(db_session, "U_TEST", "บ้าน")
    assert len(home_notes) == 1
    assert home_notes[0].note == "รหัสบ้าน"

    # no match
    none_notes = await get_notes_by_keyword(db_session, "U_TEST", "ไม่พบ")
    assert len(none_notes) == 0
