import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from services.reminder_service import get_users_without_today_log, send_daily_reminders


class TestReminderService(unittest.IsolatedAsyncioTestCase):
    async def test_get_users_without_today_log(self):
        today = date(2026, 6, 1)

        mock_db = AsyncMock()
        all_users_result = MagicMock()
        all_users_result.scalars.return_value.all.return_value = ["U1", "U2", "U3"]
        logged_result = MagicMock()
        logged_result.scalars.return_value.all.return_value = ["U1"]

        mock_db.execute = AsyncMock(side_effect=[all_users_result, logged_result])

        users = await get_users_without_today_log(mock_db, today)
        self.assertEqual(users, ["U2", "U3"])

    async def test_send_daily_reminders_skips_when_lock_not_acquired(self):
        line_api = AsyncMock()
        with patch("services.reminder_service._acquire_reminder_lock", return_value=False):
            await send_daily_reminders(line_api)
        line_api.push_message.assert_not_called()

    async def test_send_daily_reminders_sends_to_users(self):
        line_api = AsyncMock()
        with (
            patch("services.reminder_service._acquire_reminder_lock", return_value=True),
            patch("services.reminder_service.SessionLocal") as mock_session_local,
            patch("services.reminder_service.get_users_without_today_log", return_value=["U2"]),
        ):
            mock_session = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_session

            await send_daily_reminders(line_api)

        line_api.push_message.assert_called_once()
