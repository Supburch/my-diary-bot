"""Unit Tests สำหรับฟีเจอร์สรุปโน้ตย้อนหลัง (Phase F)"""
import pytest
from services.diary_service import parse_note_summary_command


class TestParseNoteSummaryCommand:
    """ทดสอบการ parse คำสั่งสรุปโน้ตจากข้อความผู้ใช้"""

    def test_thai_prefix_with_month(self):
        """สรุปโน้ต 01 → เดือน 1"""
        result = parse_note_summary_command("สรุปโน้ต 01")
        assert result == {"period_type": "month", "value": 1}

    def test_thai_prefix_with_month_december(self):
        """สรุปโน้ต 12 → เดือน 12"""
        result = parse_note_summary_command("สรุปโน้ต 12")
        assert result == {"period_type": "month", "value": 12}

    def test_thai_prefix_with_month_no_leading_zero(self):
        """สรุปโน้ต 3 → เดือน 3"""
        result = parse_note_summary_command("สรุปโน้ต 3")
        assert result == {"period_type": "month", "value": 3}

    def test_english_prefix_with_year(self):
        """note 2024 → ปี 2024"""
        result = parse_note_summary_command("note 2024")
        assert result == {"period_type": "year", "value": 2024}

    def test_thai_prefix_with_year(self):
        """สรุปโน้ต 2023 → ปี 2023"""
        result = parse_note_summary_command("สรุปโน้ต 2023")
        assert result == {"period_type": "year", "value": 2023}

    def test_no_argument_returns_current_month(self):
        """สรุปโน้ต (ไม่มีตัวเลข) → เดือนปัจจุบัน"""
        result = parse_note_summary_command("สรุปโน้ต")
        assert result == {"period_type": "current_month"}

    def test_english_no_argument(self):
        """note (ไม่มีตัวเลข) → เดือนปัจจุบัน"""
        result = parse_note_summary_command("note")
        assert result == {"period_type": "current_month"}

    def test_thai_short_prefix(self):
        """โน้ต 06 → เดือน 6"""
        result = parse_note_summary_command("โน้ต 06")
        assert result == {"period_type": "month", "value": 6}

    def test_invalid_month_too_high(self):
        """สรุปโน้ต 13 → None (เดือนไม่ถูกต้อง)"""
        result = parse_note_summary_command("สรุปโน้ต 13")
        assert result is None

    def test_invalid_month_zero(self):
        """สรุปโน้ต 0 → None (เดือน 0 ไม่มีจริง)"""
        result = parse_note_summary_command("สรุปโน้ต 0")
        assert result is None

    def test_unrelated_text(self):
        """ข้อความทั่วไปที่ไม่ใช่คำสั่ง → None"""
        result = parse_note_summary_command("สวัสดี")
        assert result is None

    def test_habit_code_not_matched(self):
        """99 → None (ไม่ใช่คำสั่งโน้ต)"""
        result = parse_note_summary_command("99")
        assert result is None

    def test_whitespace_handling(self):
        """คำสั่งมีช่องว่างเพิ่มเข้ามา"""
        result = parse_note_summary_command("  สรุปโน้ต   07  ")
        assert result == {"period_type": "month", "value": 7}
