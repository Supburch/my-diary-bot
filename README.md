# My Diary Bot

LINE Bot สำหรับติดตามนิสัยรายวัน (Habit Tracker) พร้อม Flex Message, สรุปรายสัปดาห์/เดือน, และอินโฟกราฟิกสถิติ

## ฟีเจอร์

- บันทึกนิสัยด้วยรหัส 2 หลัก (`99`, `77 3`, toggle ซ้ำเพื่อยกเลิก)
- โน้ตอิสระ (`***ข้อความ`) และสรุปโน้ต (`สรุปโน้ต 01`)
- โน้ตอิสระ เรียกกลับดูได้ด้วยคำ/คีย์เวิร์ดที่เขียนไว้ในโน้ต (พิมพ์ `wifi` / `ดู wifi` / `#wifi`)
- สรุปวันนี้ / รายสัปดาห์ / รายเดือน (Flex Message)
- อินโฟกราฟิก PNG (`สรุปภาพ`, `stats 2024`) อัปโหลด Supabase Storage
- Custom habits ต่อ user (`เพิ่ม 12 วิ่ง 🏃`)
- Streak (ต่อเนื่องปัจจุบัน + สถิติสูงสุด)
- Daily reminder push (APScheduler, ค่าเริ่มต้น 22:00 น.)

## Tech Stack

| ส่วน | เทคโนโลยี |
|------|-----------|
| Web framework | FastAPI + Uvicorn/Gunicorn |
| LINE SDK | line-bot-sdk v3 (async) |
| Database | PostgreSQL (Supabase) / SQLite (dev fallback) |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| Image | Pillow + Kanit font |
| Storage | Supabase Storage (signed URL) |
| Scheduler | APScheduler |
| Lock (optional) | Redis |

## โครงสร้างโปรเจกต์

```
app.py                  # FastAPI entry, webhook, health, scheduler
handlers/
  message_handler.py    # รับ LINE event, ส่ง reply
services/
  diary_service.py      # แกนประมวลผลคำสั่ง
  infographic_service.py
  reminder_service.py
flex/
  flex_builders.py      # Flex Message + Quick Reply
db/
  database.py
  models.py
config/
  user_habits.py        # default habit codes
alembic/                # database migrations
tests/
```

## การติดตั้ง (Local)

```bash
# 1. Clone และติดตั้ง dependencies
pip install -r requirements.txt

# 2. คัดลอก env
cp env.example .env
# แก้ไข LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET ใน .env

# 3. รัน migration (optional — app จะ create_all ตอน startup ด้วย)
alembic upgrade head

# 4. รัน dev server
uvicorn app:app --reload --port 8000
```

### Environment Variables

| ตัวแปร | บังคับ | คำอธิบาย |
|--------|--------|----------|
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINE Messaging API token |
| `LINE_CHANNEL_SECRET` | ✅ | LINE channel secret |
| `DATABASE_URL` | ❌ | PostgreSQL URL (ไม่ตั้ง = SQLite local) |
| `SUPABASE_URL` | ❌ | สำหรับ infographic storage |
| `SUPABASE_SERVICE_ROLE_KEY` | ❌ | Supabase service role key |
| `REDIS_URL` | ❌ | Redis สำหรับ reminder lock |
| `REMINDER_HOUR` | ❌ | ชั่วโมงส่ง reminder (default: 22) |
| `REMINDER_ENABLED` | ❌ | เปิด/ปิด reminder (default: true) |
| `KEEP_ALIVE_URL` | ❌ | Self-ping URL ป้องกัน Render spin-down |

## คำสั่งที่ใช้บ่อย

| พิมพ์ | ผลลัพธ์ |
|-------|---------|
| `99` | Toggle นิสัยรหัส 99 |
| `สรุป` / `วันนี้` | สรุปวันนี้ |
| `weekly` / `สัปดาห์` | สรุป 7 วัน |
| `monthly` / `เดือน` | สรุป 30 วัน |
| `สรุปภาพ` | อินโฟกราฟิกเดือนปัจจุบัน |
| `***โน้ต` | บันทึกโน้ต |
| `wifi` / `ดู wifi` / `#wifi` | เรียกดูโน้ตที่มีคำ `wifi` อยู่ในเนื้อหาโน้ต |
| `help` / `เมนู` | เมนูช่วยเหลือ |
| `เพิ่ม 12 ชื่อ 🏃` | เพิ่ม custom habit |

## Deploy (Render)

ใช้ `render.yaml` ที่มีอยู่แล้ว — สำคัญ:

- **workers=1** — APScheduler ต้องรัน single worker
- `alembic upgrade head` รันก่อน start อัตโนมัติ
- ตั้ง `KEEP_ALIVE_URL` เป็น URL ของ service เอง

## ทดสอบ

```bash
python -m pytest tests/ -v
```

## API Endpoints

| Method | Path | คำอธิบาย |
|--------|------|----------|
| GET | `/ping` | Health ping + version |
| GET | `/health` | DB status + uptime |
| POST | `/callback` | LINE webhook |

## Default Habit Codes

| รหัส | กิจกรรม |
|------|---------|
| 00 | News/Talk |
| 11 | 5min Read |
| 22 | Documentary |
| 33 | PU @ 10 |
| 44 | Squad @ 35 |
| 55 | Walk 2Km |
| 66 | Trade/Invest |
| 77 | Mindfulness |
| 88 | Farm/House |
| 99 | AI Coding |

Custom habits จะทับ default ของรหัสเดียวกันได้
