import os
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# ดึงค่า URL ของฐานข้อมูล
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ตั้งค่าสถานะ Fallback Mode และ Dialect Type
IS_FALLBACK_MODE = False
DB_DIALECT = "postgresql"

if not DATABASE_URL:
    # เปิดโหมด Emergency Development Fallback เฉพาะตอนที่ไม่มี Env (เช่น รันเครื่องตัวเอง)
    DATABASE_URL = "sqlite+aiosqlite:///./diary.db"
    IS_FALLBACK_MODE = True
    DB_DIALECT = "sqlite"
    logger.warning(
        "DATABASE_URL not found! Emergency Development Fallback activated using SQLite.",
        extra={"primary": "postgresql", "fallback": "sqlite"}
    )
else:
    # แปลง postgresql:// เป็น postgresql+asyncpg:// สำหรับ Driver Async
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    if "postgresql" in DATABASE_URL:
        DB_DIALECT = "postgresql"
    else:
        DB_DIALECT = "sqlite"

logger.info(f"Database Engine configured for Dialect: {DB_DIALECT} | Fallback Mode: {IS_FALLBACK_MODE}")

# ตั้งค่าความปลอดภัยสำหรับ Connection Pool
if DB_DIALECT == "sqlite":
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"timeout": 30},
    )
else:
    # Supabase (PostgreSQL) Pool settings — รัดกุมสำหรับ Free Tier
    engine = create_async_engine(
        DATABASE_URL,
        pool_size=int(os.environ.get("POOL_SIZE", 2)),
        max_overflow=int(os.environ.get("MAX_OVERFLOW", 3)),
        pool_recycle=int(os.environ.get("POOL_RECYCLE", 1800)),
        pool_pre_ping=True,
    )

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def check_db_health() -> bool:
    """ตรวจสอบสุขภาพความฟิตของฐานข้อมูลโดยสั่ง SELECT 1"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed for dialect {DB_DIALECT}: {e}")
        return False
