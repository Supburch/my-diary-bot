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

USER_COMMAND_MAPS: dict[str, dict[str, str]] = {
    # ตัวอย่างการกำหนดรหัสเฉพาะบุคคลสำหรับผู้ใช้ต่างๆ (User-specific command mapping)
    # คีย์คือ user_id และค่าคือพจนานุกรมรหัส Habit
    # "U123456789abcdef...": {
    #     "00": "เริ่มทำ IF",
    #     "11": "5min Read",
    #     "22": "Documentary",
    # }
}

def get_command_map(user_id: str) -> dict[str, str]:
    """ดึงแผนผังคำสั่ง (Habit Mapping) ตามรายผู้ใช้งานจากระบบ Config
    เพื่อรองรับการเปลี่ยนรหัสเฉพาะบุคคลอย่างอิสระและยืดหยุ่น
    """
    if not user_id:
        return DEFAULT_COMMAND_MAP
    return USER_COMMAND_MAPS.get(user_id, DEFAULT_COMMAND_MAP)
