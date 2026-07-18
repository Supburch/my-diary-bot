from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import UserHabit

DEFAULT_COMMAND_MAP: dict[str, str] = {
    "00": "News/Talk",
    "11": "5min Read",
    "22": "Documentary",
    "33": "PU @ 10",
    "44": "Squad @ 35",
    "55": "Walk 2Km",
    "66": "Trade/Invest",
    "77": "Mindfulness",
    "88": "Farm/House",
    "99": "AI Coding",
}

async def get_command_map(db: AsyncSession, user_id: str) -> dict[str, str]:
    """ดึงแผนผังคำสั่ง (Habit Mapping) ตามรายผู้ใช้งานจากระบบ Database"""
    if not user_id:
        return DEFAULT_COMMAND_MAP.copy()

    # ดึงค่าจากตาราง UserHabit
    result = await db.execute(select(UserHabit).where(UserHabit.user_id == user_id))
    user_habits = result.scalars().all()

    # ใช้ Default เป็นฐาน
    command_map = DEFAULT_COMMAND_MAP.copy()
    
    # เสริม/ทับด้วย Custom Habits
    for habit in user_habits:
        command_map[habit.code] = habit.category

    return command_map

async def get_habit_icons(db: AsyncSession, user_id: str) -> dict[str, str]:
    """ดึงไอคอน Custom จาก Database"""
    if not user_id:
        return {}
        
    result = await db.execute(select(UserHabit).where(UserHabit.user_id == user_id))
    user_habits = result.scalars().all()

    icon_map = {}
    for habit in user_habits:
        icon_map[habit.code] = habit.icon

    return icon_map
