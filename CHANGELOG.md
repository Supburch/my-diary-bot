# Changelog

บันทึกการอัปเดตงานของ My Diary Bot เรียงจากใหม่ไปเก่า

## [2026-08-17] โน้ตด้วยคีย์เวิร์ด (Keyword Notes)

**ฟีเจอร์ใหม่:** บันทึกโน้ตพร้อมคีย์เวิร์ด และเรียกกลับมาดูได้ด้วยคีย์เวิร์ด

### วิธีใช้
- **บันทึกโน้ตพร้อมคีย์เวิร์ด:** `***keyword: เนื้อหา` เช่น `***wifi: รหัสผ่านคือ 1234`
- **เรียกกลับดู:** พิมพ์คีย์เวิร์ดตรงๆ (`wifi`), หรือ `ดู wifi` / `หา wifi` / `ค้น wifi` / `#wifi`
- โน้ตเดิม `***ข้อความ` ยังใช้ได้เหมือนเดิม (ไม่มีคีย์เวิร์ด)

### รายละเอียดการแก้ไข
- `db/models.py` — เพิ่มคอลัมน์ `keyword` (String 255, nullable, index) ใน `DiaryEntry`
- `alembic/versions/002_add_note_keyword.py` — migration ใหม่ (idempotent, add column + index)
- `services/diary_service.py`
  - `split_keyword_note()` — แยก `keyword: เนื้อหา` (คีย์เวิร์ดต้องเป็นคำเดียว ไม่มีช่องว่าง)
  - `parse_keyword_recall()` — parse คำสั่งค้นหา (กันรหัส habit 2 หลักไม่ให้ถูกมองเป็นคีย์เวิร์ด)
  - `get_notes_by_keyword()` — query แบบ case-insensitive
  - เพิ่ม logic ค้นหาคีย์เวิร์ดใน `process_message` ก่อน habit toggle
- `tests/test_note_keyword.py` — เทสต์ใหม่ (unit + integration) 30 ข้อ
- `README.md` — เพิ่มเอกสารการใช้งาน

### หมายเหตุ
- ฐานข้อมูลเดิมต้องรัน `alembic upgrade head` เพื่อเพิ่มคอลัมน์ (Render รันอัตโนมัติ)
- เทสต์ทั้งหมดผ่าน: **54 passed**
