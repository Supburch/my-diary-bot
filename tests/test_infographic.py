import os
import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from services.diary_service import parse_infographic_command
from services.infographic_service import (
    render_infographic_sync,
    ensure_infographics_bucket_exists,
    generate_and_upload_infographic,
    ensure_fonts_downloaded
)

class TestInfographicGenerator(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # ข้อมูลจำลองความสำเร็จสำหรับทดสอบ
        self.user_id = "U_TEST_USER_INFO"
        self.period_label = "สถิตินิสัยเดือนมิถุนายน 2026"
        self.stats = {
            "completion_rate": 85,
            "active_days": 17,
            "total_days": 20,
            "total_checkmarks": 42,
            "top_habit_name": "AI Coding",
            "top_habit_freq": 15,
            "current_streak": 5,
            "longest_streak": 12,
        }
        self.habit_breakdown = [
            {"code": "99", "name": "AI Coding", "count": 15, "pct": 75},
            {"code": "77", "name": "Mindfulness", "count": 10, "pct": 50},
            {"code": "00", "name": "News/Talk", "count": 8, "pct": 40},
            {"code": "11", "name": "5min Read", "count": 5, "pct": 25},
            {"code": "55", "name": "Walk 2Km", "count": 4, "pct": 20},
        ]
        # จำลองตาราง Contribution
        self.contribution_data = {
            date(2026, 6, 1): 3,
            date(2026, 6, 2): 1,
            date(2026, 6, 3): 0,
            date(2026, 6, 4): 2,
            date(2026, 6, 5): 4,
        }
        self.start_date = date(2026, 6, 1)
        self.end_date = date(2026, 6, 20)

    def test_parse_infographic_command_success(self):
        # 1. ทดสอบพิมพ์เปล่าๆ
        self.assertEqual(parse_infographic_command("สรุปภาพ"), {"period_type": "current_month"})
        self.assertEqual(parse_infographic_command("stats"), {"period_type": "current_month"})
        self.assertEqual(parse_infographic_command("ig"), {"period_type": "current_month"})
        
        # 2. ทดสอบแบบระบุเดือน
        self.assertEqual(parse_infographic_command("สรุปภาพ 01"), {"period_type": "month", "value": 1})
        self.assertEqual(parse_infographic_command("stats 5"), {"period_type": "month", "value": 5})
        self.assertEqual(parse_infographic_command("ig 12"), {"period_type": "month", "value": 12})
        
        # 3. ทดสอบแบบระบุปี ค.ศ.
        self.assertEqual(parse_infographic_command("สรุปภาพ 2024"), {"period_type": "year", "value": 2024})
        self.assertEqual(parse_infographic_command("stats 2026"), {"period_type": "year", "value": 2026})

    def test_parse_infographic_command_invalid(self):
        # 1. เดือนเกินขอบเขต
        self.assertIsNone(parse_infographic_command("สรุปภาพ 13"))
        self.assertIsNone(parse_infographic_command("stats 00"))
        
        # 2. คำสั่งไม่ตรง/พิมพ์เล่น
        self.assertIsNone(parse_infographic_command("สรุปภาพขำๆ"))
        self.assertIsNone(parse_infographic_command("สลัดผัก"))
        self.assertIsNone(parse_infographic_command("99"))

    def test_render_infographic_sync_returns_png_bytes(self):
        # ตรวจสอบการทำความสะอาดและดาวน์โหลดฟอนต์ระบบมาก่อนวาด
        ensure_fonts_downloaded()
        
        # สั่งวาดจริงแบบ Sync
        image_bytes = render_infographic_sync(
            self.period_label,
            self.stats,
            self.habit_breakdown,
            self.contribution_data,
            self.start_date,
            self.end_date
        )
        
        # ตรวจดู Header ไบนารีของรูป PNG (ต้องขึ้นต้นด้วย \x89PNG\r\n\x1a\n)
        self.assertIsInstance(image_bytes, bytes)
        self.assertTrue(len(image_bytes) > 1000, "Image bytes should be reasonably sized.")
        self.assertEqual(image_bytes[:4], b"\x89PNG")

    @patch("services.infographic_service.httpx.AsyncClient")
    async def test_ensure_infographics_bucket_exists_already_there(self, mock_client_cls):
        # จำลองการตรวจสอบแล้วพบว่า Bucket มีอยู่แล้ว (200 OK)
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(status_code=200)
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        
        with patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "testkey"}):
            res = await ensure_infographics_bucket_exists()
            self.assertTrue(res)
            mock_client.get.assert_called_once_with(
                "https://test.supabase.co/storage/v1/bucket/infographics",
                headers={"Authorization": "Bearer testkey", "Content-Type": "application/json"},
                timeout=10.0
            )
            # ไม่ควรต้องสร้างใหม่
            mock_client.post.assert_not_called()

    @patch("services.infographic_service.httpx.AsyncClient")
    async def test_ensure_infographics_bucket_creation_success(self, mock_client_cls):
        # จำลองเมื่อไม่พบ bucket (404) และทำการสร้างใหม่สำเร็จ (200 OK)
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(status_code=404)
        mock_client.post.return_value = MagicMock(status_code=200)
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        
        with patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "testkey"}):
            res = await ensure_infographics_bucket_exists()
            self.assertTrue(res)
            # มีการยิงเช็คและยิงสร้าง
            mock_client.get.assert_called_once()
            mock_client.post.assert_called_once()

    @patch("services.infographic_service.httpx.AsyncClient")
    async def test_generate_and_upload_infographic_missing_env(self, mock_client_cls):
        # หากไม่มี env variables
        with patch.dict(os.environ, {}, clear=True):
            url = await generate_and_upload_infographic(
                self.user_id, self.period_label, self.stats,
                self.habit_breakdown, self.contribution_data,
                self.start_date, self.end_date
            )
            self.assertIsNone(url)

    @patch("services.infographic_service.httpx.AsyncClient")
    async def test_generate_and_upload_infographic_success(self, mock_client_cls):
        # จำลองการอัปโหลดไฟล์ (200) และขอสร้าง Signed URL (200) สำเร็จ
        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            MagicMock(status_code=200), # อัปโหลดสำเร็จ
            MagicMock(status_code=200, json=lambda: {"signedURL": "/storage/v1/object/sign/infographics/test.png?token=123"}) # ขอ Signed URL สำเร็จ
        ]
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        
        with patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "testkey"}):
            url = await generate_and_upload_infographic(
                self.user_id, self.period_label, self.stats,
                self.habit_breakdown, self.contribution_data,
                self.start_date, self.end_date
            )
            self.assertIsNotNone(url)
            self.assertEqual(url, "https://test.supabase.co/storage/v1/storage/v1/object/sign/infographics/test.png?token=123")
            self.assertEqual(mock_client.post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
