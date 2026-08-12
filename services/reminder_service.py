import logging
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from linebot.v3.messaging import AsyncMessagingApi, PushMessageRequest, TextMessage
from sqlalchemy import distinct, select

from db.database import SessionLocal
from db.models import DiaryEntry

logger = logging.getLogger(__name__)

BANGKOK = ZoneInfo("Asia/Bangkok")
REMINDER_LOCK_KEY = "diarybot:reminder:daily"
REMINDER_LOCK_TTL = int(os.environ.get("REDIS_LOCK_TTL_SEC", "3600"))


def today_bkk() -> date:
    return datetime.now(BANGKOK).date()


async def _acquire_reminder_lock() -> bool:
    """ใช้ Redis lock ป้องกัน reminder ยิงซ้ำ (optional — ข้ามได้ถ้าไม่มี REDIS_URL)"""
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        return True

    try:
        from redis.asyncio import Redis

        client = Redis.from_url(redis_url, decode_responses=True)
        try:
            acquired = await client.set(
                REMINDER_LOCK_KEY,
                "1",
                nx=True,
                ex=REMINDER_LOCK_TTL,
            )
            return bool(acquired)
        finally:
            await client.aclose()
    except Exception:
        logger.exception("Redis lock failed — skipping reminder to avoid duplicates")
        return False


async def get_users_without_today_log(db, today: date) -> list[str]:
    """คืน user_id ที่เคยใช้งานแต่ยังไม่บันทึก habit วันนี้ (ไม่นับ note)"""
    users_stmt = select(distinct(DiaryEntry.user_id))
    all_users = list((await db.execute(users_stmt)).scalars().all())

    if not all_users:
        return []

    logged_stmt = select(distinct(DiaryEntry.user_id)).where(
        DiaryEntry.entry_date == today,
        DiaryEntry.done.is_(True),
        ~DiaryEntry.code.like("~~%"),
    )
    logged_today = set((await db.execute(logged_stmt)).scalars().all())

    return [uid for uid in all_users if uid not in logged_today]


async def send_daily_reminders(line_api: AsyncMessagingApi) -> None:
    """ส่ง push reminder ให้ user ที่ยังไม่บันทึก habit วันนี้ (รันตาม REMINDER_HOUR)"""
    if not await _acquire_reminder_lock():
        logger.info("Daily reminder skipped — another instance holds the lock")
        return

    today = today_bkk()
    logger.info(f"Running daily reminder job for {today}")

    async with SessionLocal() as db:
        users = await get_users_without_today_log(db, today)

    if not users:
        logger.info("Daily reminder: all active users already logged today")
        return

    message = TextMessage(
        text=(
            "🔔 เย็นนี้ยังไม่ได้บันทึกนิสัยเลยนะ\n"
            "พิมพ์รหัส 2 หลัก (เช่น 99) หรือพิมพ์ สรุป เพื่อดูความคืบหน้าวันนี้"
        )
    )

    sent = 0
    for user_id in users:
        try:
            await line_api.push_message(
                PushMessageRequest(to=user_id, messages=[message])
            )
            sent += 1
        except Exception:
            logger.exception(f"Failed to send reminder to user {user_id}")

    logger.info(f"Daily reminder sent to {sent}/{len(users)} users")
