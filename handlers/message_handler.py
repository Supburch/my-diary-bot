import logging
import asyncio
from linebot.v3.messaging import (
    AsyncMessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
    ImageMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from sqlalchemy.ext.asyncio import AsyncSession
from services.diary_service import process_message

logger = logging.getLogger(__name__)

async def reply_message(line_api: AsyncMessagingApi, reply_token: str, response: str | dict) -> None:
    """ส่งกลับข้อความหาผู้ใช้ผ่าน LINE API รองรับทั้งข้อความธรรมดา (str/dict) และ Flex Message (dict)
    พร้อมระบบ JSON Validation + Fallback สองชั้น (compile-time และ send-time) เพื่อให้บอตไม่เงียบหาย
    """
    # สกัดปุ่ม Quick Reply (ถ้ามีระบุใน response)
    quick_reply = None
    if isinstance(response, dict):
        quick_reply = response.get("quick_reply")

    messages = None
    fallback_text = None

    if isinstance(response, dict) and response.get("type") == "flex":
        alt_text = response.get("alt_text", "Habit Tracker Update")
        bubble_contents = response.get("contents")
        fallback_text = response.get("fallback_text", alt_text)

        try:
            # [CRITICAL CHECK] ทดสอบคอมไพล์โครงสร้าง Flex Message ก่อนส่งจริง
            container = FlexContainer.from_dict(bubble_contents)
            messages = [FlexMessage(alt_text=alt_text, contents=container, quick_reply=quick_reply)]
            logger.info(f"Successfully compiled Flex Message: {alt_text}")
        except Exception as e:
            # [ROBUST FALLBACK #1] Flex พังตอน compile → ส่งข้อความธรรมดาแทน
            logger.error(f"LINE Flex validation failed! Falling back to text message. Error: {e}")
            messages = [TextMessage(text=fallback_text[:2000], quick_reply=quick_reply)]
    elif isinstance(response, dict) and response.get("type") == "image":
        # ส่งรูปภาพอินโฟกราฟิก
        original_url = response.get("original_content_url")
        preview_url = response.get("preview_image_url", original_url)
        fallback_text = response.get("fallback_text") or "📊 สรุปสถิติของคุณ"
        messages = [
            ImageMessage(
                original_content_url=original_url,
                preview_image_url=preview_url,
                quick_reply=quick_reply,
            )
        ]
        logger.info(f"Successfully compiled Image Message: {original_url}")
    else:
        # ข้อความธรรมดา
        if isinstance(response, dict) and response.get("type") == "text":
            text_content = response.get("text", "")
        else:
            text_content = str(response)

        fallback_text = text_content
        messages = [TextMessage(text=text_content[:2000], quick_reply=quick_reply)]
        logger.info("Sending Text Message response.")

    if messages is None:
        logger.error("reply_message: ไม่มีข้อความที่พร้อมส่ง")
        return

    try:
        await asyncio.wait_for(
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=messages,
                )
            ),
            timeout=30,
        )
    except Exception:
        # [ROBUST FALLBACK #2] ถ้าส่ง Flex/Image ล้มเหลวที่ระดับ API (เช่น LINE reject / timeout / token หมดอายุ)
        # ให้ลองส่งข้อความธรรมดาแทน — reply_token ใช้ได้ครั้งเดียว LINE จะ reject การใช้ซ้ำเองโดยอัตโนมัติ
        logger.exception("reply_message error — attempting plain text fallback")
        if fallback_text:
            try:
                await asyncio.wait_for(
                    line_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text=fallback_text[:2000])],
                        )
                    ),
                    timeout=30,
                )
                logger.info("Plain text fallback sent successfully")
            except Exception:
                logger.exception("reply_message fallback also failed")


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
