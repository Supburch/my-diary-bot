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
    """ส่งกลับข้อความหาผู้ใช้ผ่าน LINE API รองรับทั้งข้อความธรรมดา (str/dict) และ Flex Message (dict)
    พร้อมมีระบบ JSON Validation และ Fallback เพื่อความปลอดภัยสูงสุดในโปรดักชัน
    """
    try:
        if isinstance(response, dict) and response.get("type") == "flex":
            alt_text = response.get("alt_text", "Habit Tracker Update")
            bubble_contents = response.get("contents")
            fallback_text = response.get("fallback_text", alt_text)
            
            try:
                # [CRITICAL CHECK] ทำการทดสอบคอมไพล์โครงสร้าง Flex Message
                container = FlexContainer.from_dict(bubble_contents)
                messages = [FlexMessage(alt_text=alt_text, contents=container)]
                logger.info(f"Successfully compiled and sending Flex Message: {alt_text}")
            except Exception as e:
                # [ROBUST FALLBACK] หาก Flex พังจากการประมวลผล จะทำการส่งข้อความธรรมดากลับไปทันทีเพื่อให้บอตไม่เงียบหาย
                logger.error(f"LINE Flex validation failed! Falling back to text message. Error: {e}")
                messages = [TextMessage(text=fallback_text[:2000])]
        else:
            # ดึงข้อความดิบ
            if isinstance(response, dict) and response.get("type") == "text":
                text_content = response.get("text", "")
            else:
                text_content = str(response)
                
            messages = [TextMessage(text=text_content[:2000])]
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
