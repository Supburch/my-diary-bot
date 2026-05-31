import logging
import asyncio
from linebot.v3.messaging import (
    AsyncMessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from sqlalchemy.ext.asyncio import AsyncSession
from services.diary_service import process_message

logger = logging.getLogger(__name__)

async def reply_message(line_api: AsyncMessagingApi, reply_token: str, text: str) -> None:
    """ส่งกลับข้อความหาผู้ใช้ผ่าน LINE API"""
    try:
        await asyncio.wait_for(
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=text[:2000])],
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
