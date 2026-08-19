# Changelog

บันทึกการอัปเดตงานของ My Diary Bot เรียงจากใหม่ไปเก่า

## [2026-08-19] ลบฟีเจอร์โน้ตแบบ `***keyword: เนื้อหา`

**ลบ:** ฟีเจอร์บันทึกโน้ตพร้อมคีย์เวิร์ด (`***keyword: เนื้อหา`) และคอลัมน์ `keyword` ออกทั้งหมด

### รายละเอียด
- `db/models.py` — ลบคอลัมน์ `keyword` ออกจาก `DiaryEntry`
- `alembic/versions/003_remove_note_keyword.py` — migration ใหม่ (idempotent) สำหรับ drop column + index
- `services/diary_service.py` — ลบ `split_keyword_note()`, แก้ `get_notes_by_keyword()` ให้ค้นจากเนื้อหาโน้ต (`note`) อย่างเดียว
- `tests/test_note_keyword.py` — ลบเทสต์ `split_keyword_note`, ปรับเทสต์ให้ค้นจากเนื้อหาโน้ต
- `README.md` — ลบวิธีใช้ `***keyword: เนื้อหา`

### วิธีใช้โน้ต (หลังแก้)
- บันทึกโน้ต: `***ข้อความ`
- เรียกดูโน้ตด้วยคำที่อยู่ในโน้ต: พิมพ์คำตรงๆ (`wifi`), `ดู wifi`, `หา wifi`, `ค้น wifi`, หรือ `#wifi`

## [2026-08-19] ค้นโน้ตด้วยคำที่เขียนในเนื้อหาโน้ต

**ปรับปรุง:** เรียกดูโน้ตด้วยคีย์เวิร์ดได้จากคำที่เขียนอยู่ในโน้ตโดยตรง ไม่ต้องตั้งคีย์เวิร์ดแยกตอนบันทึก

### รายละเอียด
- `services/diary_service.py` — `get_notes_by_keyword()` ค้นหาแบบ substring ในเนื้อหาโน้ต (`note`) ร่วมกับคอลัมน์ `keyword` เดิม (case-insensitive) และจำกัดเฉพาะรายการโน้ต (`code ~~%`)
- รองรับโน้ตทั่วไป เช่น `*** รหัส wifi อยู่หลังเราเตอร์` แล้วพิมพ์ `wifi` หรือ `ดู wifi` / `#wifi` เพื่อเรียกดูได้เลย
- โน้ตแบบ `***keyword: เนื้อหา` เดิมยังใช้ได้เหมือนเดิม
- `tests/test_note_keyword.py` — เพิ่มเทสต์ค้นหาจากเนื้อหาโน้ต

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
