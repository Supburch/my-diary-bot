import logging
import asyncio
from linebot.v3.messaging import (
    AsyncMessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from sqlalchemy.ext.asyncio import AsyncSession
from services.diary_service import process_message

logger = logging.getLogger(__name__)

async def reply_message(line_api: AsyncMessagingApi, reply_token: str, response: str | dict) -> None:
    """ส่งกลับข้อความหาผู้ใช้ผ่าน LINE API รองรับทั้งข้อความธรรมดา (str) และ Flex Message (dict)"""
    try:
        if isinstance(response, dict):
            # กำหนดข้อความการแจ้งเตือนล็อกหน้าจอ (Alt Text) ตามประเภทเนื้อหา
            alt_text = "Habit Tracker"
            if "HABIT TRACKER CODES" in str(response):
                alt_text = "📋 รายการรหัส Habit"
            elif "DAILY DIARY" in str(response):
                alt_text = "📅 สรุปประวัติไดอารี่ประจำวัน"
            elif "บันทึกความสำเร็จ!" in str(response) or "ยกเลิกบันทึกแล้ว" in str(response):
                alt_text = "📝 อัปเดตความสำเร็จ Habit"

            container = FlexContainer.from_dict(response)
            messages = [FlexMessage(alt_text=alt_text, contents=container)]
            logger.info("Sending Flex Message response.")
        else:
            messages = [TextMessage(text=response[:2000])]
            logger.info("Sending Text Message response.")

        await asyncio.wait_for(
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=messages,
                )
            ),
            timeout=10,
        )
    except Exception:
        logger.exception("reply_message error")


async def handle_webhook_event(
    event: MessageEvent,
    db: AsyncSession,
    line_api: AsyncMessagingApi,
) -> None:
    """ควบคุมจัดการคัดกรองและประมวลผลข้อความจาก Webhook Event"""
    if not isinstance(event, MessageEvent):
        return

    if not isinstance(event.message, TextMessageContent):
        return

    user_id = getattr(event.source, "user_id", None)
    if not user_id:
        return

    text = event.message.text.strip()
    logger.info(f"Received text message from user {user_id}: {text}")

    try:
        response = await process_message(db, user_id, text)
    except Exception:
        logger.exception("process_message error")
        response = "❌ เกิดข้อผิดพลาด กรุณาลองใหม่"

    await reply_message(line_api, event.reply_token, response)
