import os
import logging
import asyncio
import urllib.request
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont
import httpx

logger = logging.getLogger(__name__)

# คอนฟิกหลักของระบบจัดเก็บภาพและควบคุม Concurrency
THREAD_EXECUTOR = ThreadPoolExecutor(max_workers=2)
CONCURRENCY_SEMAPHORE = asyncio.Semaphore(2)

FONT_DIR = "fonts"
REGULAR_FONT_PATH = os.path.join(FONT_DIR, "NotoSansThai-Regular.ttf")
BOLD_FONT_PATH = os.path.join(FONT_DIR, "NotoSansThai-Bold.ttf")

# สีหลักของธีม Zen Slate & Emerald
COLOR_BG = "#0F172A"       # Slate 900
COLOR_CARD = "#1E293B"     # Slate 800
COLOR_BORDER = "#334155"   # Slate 700
COLOR_TEXT_PRI = "#F8FAFC" # Slate 50
COLOR_TEXT_SEC = "#94A3B8" # Slate 400

# สีเน้น (Accent Colors)
COLOR_EMERALD = "#34D399"  # Emerald 400 (อัตราสำเร็จ / ความคืบหน้า)
COLOR_SKY = "#38BDF8"      # Sky 400 (เช็คลิสต์รวม)
COLOR_AMBER = "#F59E0B"    # Amber 500 (Streak / ไฟลุก)
COLOR_PURPLE = "#C084FC"   # Purple 400 (นิสัยยอดฮิต)

# สีความเข้มข้นของตารางตาราง Contribution
CONTRIBUTION_COLORS = {
    0: "#334155",  # Slate 700 (ยังไม่ได้ทำ)
    1: "#065F46",  # Dark green
    2: "#047857",  # Medium green
    3: "#10B981",  # Bright emerald
    4: "#34D399",  # Light emerald (4+ checkmarks)
}

def ensure_fonts_downloaded():
    """ตรวจสอบว่าฟอนต์ Noto Sans Thai ได้ถูกติดตั้งและจัดเตรียมทางกายภาพในโฟลเดอร์ fonts/ แล้ว"""
    if not os.path.exists(REGULAR_FONT_PATH) or not os.path.exists(BOLD_FONT_PATH):
        logger.warning(
            "Noto Sans Thai font files are missing from fonts/ directory! "
            "Pillow will fallback to system default fonts."
        )

def draw_wrapped_text(draw, text, x, y, max_width, font, fill):
    """ฟังก์ชันช่วยตัดบรรทัดข้อความภาษาไทยเพื่อไม่ให้ล้นการ์ด"""
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip()
        # วัดขนาดความกว้างข้อความ
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
            
    if current_line:
        lines.append(current_line)
        
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        current_y += h + 4
        
    return current_y

def render_infographic_sync(
    period_label: str,
    stats: dict,
    habit_breakdown: list,
    contribution_data: dict,
    start_date: date,
    end_date: date
) -> bytes:
    """วาดอินโฟกราฟิกความสำเร็จด้วย Pillow ในโหมด Synchronous (CPU-bound)"""
    ensure_fonts_downloaded()
    
    # พยายามโหลดฟอนต์ตามขนาดต่างๆ หรือโหลดฟอนต์ Default ของระบบหากโหลดไม่ผ่าน
    try:
        font_title = ImageFont.truetype(BOLD_FONT_PATH, 28)
        font_sub = ImageFont.truetype(REGULAR_FONT_PATH, 16)
        font_card_val = ImageFont.truetype(BOLD_FONT_PATH, 24)
        font_card_lbl = ImageFont.truetype(REGULAR_FONT_PATH, 13)
        font_sec_title = ImageFont.truetype(BOLD_FONT_PATH, 18)
        font_body = ImageFont.truetype(REGULAR_FONT_PATH, 14)
        font_footer = ImageFont.truetype(REGULAR_FONT_PATH, 12)
    except Exception as e:
        logger.warning(f"Unable to load Noto Sans Thai fonts ({e}). Falling back to system default font.")
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_card_val = ImageFont.load_default()
        font_card_lbl = ImageFont.load_default()
        font_sec_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_footer = ImageFont.load_default()

    # สร้างรูปภาพขนาด 800x1000 pixels โทนสีเข้ม
    img = Image.new("RGB", (800, 1000), color=COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    # ---------------------------------------------------------
    # 1. Header Section
    # ---------------------------------------------------------
    # วาด Title บรรทัดแรก
    draw.text((40, 35), "DAILY HABITS REPORT", font=font_title, fill=COLOR_TEXT_PRI)
    
    # วาด Subtitle แสดงระยะเวลา
    date_str = f"ช่วงเวลา: {start_date.strftime('%Y-%m-%d')} ถึง {end_date.strftime('%Y-%m-%d')}"
    draw.text((40, 75), f"{period_label} | {date_str}", font=font_sub, fill=COLOR_TEXT_SEC)
    
    # วาดเส้นแบ่งบอร์ด
    draw.line([(40, 115), (760, 115)], fill=COLOR_CARD, width=2)
    
    # ---------------------------------------------------------
    # 2. Overview Metrics Cards Grid (2x2)
    # ---------------------------------------------------------
    card_w = 345
    card_h = 100
    gap = 30
    
    # พิกัดการ์ดทั้ง 4 ตัว
    cards = [
        # (x, y, title, value, label, color)
        (
            40, 135, 
            "อัตราความสำเร็จ", 
            f"{stats.get('completion_rate', 0)}%", 
            f"บันทึก {stats.get('active_days', 0)}/{stats.get('total_days', 0)} วัน", 
            COLOR_EMERALD
        ),
        (
            40 + card_w + gap, 135, 
            "เช็คลิสต์รวมทั้งหมด", 
            f"{stats.get('total_checkmarks', 0)} ครั้ง", 
            f"เฉลี่ย {stats.get('total_checkmarks', 0) / max(stats.get('total_days', 1), 1):.1f} ครั้ง/วัน", 
            COLOR_SKY
        ),
        (
            40, 135 + card_h + gap, 
            "บันทึกต่อเนื่องปัจจุบัน", 
            f"{stats.get('current_streak', 0)} วัน 🔥", 
            f"ทำสถิติสูงสุด: {stats.get('longest_streak', 0)} วัน 🏆", 
            COLOR_AMBER
        ),
        (
            40 + card_w + gap, 135 + card_h + gap, 
            "พฤติกรรมยอดฮิต", 
            f"{stats.get('top_habit_name', 'ไม่มี')}", 
            f"ทำสำเร็จไป {stats.get('top_habit_freq', 0)} ครั้ง", 
            COLOR_PURPLE
        )
    ]
    
    for x, y, title, val, lbl, color in cards:
        # วาดกล่องการ์ดมน
        draw.rounded_rectangle(
            [(x, y), (x + card_w, y + card_h)],
            radius=12,
            fill=COLOR_CARD,
            outline=COLOR_BORDER,
            width=1
        )
        
        # วาดชื่อหัวข้อการ์ด
        draw.text((x + 15, y + 15), title, font=font_card_lbl, fill=COLOR_TEXT_SEC)
        
        # จัดการตัดขนาดคำหากพฤติกรรมยาวเกินไปเพื่อไม่ให้ล้นการ์ด
        if len(val) > 16:
            val = val[:14] + "..."
            
        # วาดค่าข้อมูลขนาดใหญ่
        draw.text((x + 15, y + 35), val, font=font_card_val, fill=color)
        
        # วาดสถิติย่อยด้านล่าง
        draw.text((x + 15, y + 70), lbl, font=font_card_lbl, fill=COLOR_TEXT_SEC)

    # ---------------------------------------------------------
    # 3. Habit Breakdown Progress Bars (สถิติรายข้อ)
    # ---------------------------------------------------------
    breakdown_y = 410
    draw.text((40, breakdown_y), "สถิติรายพฤติกรรม (Habit Breakdown)", font=font_sec_title, fill=COLOR_TEXT_PRI)
    
    # จำกัดแสดงแค่ 5 อันดับแรกเพื่อไม่ให้รูปยาวล้น
    display_habits = habit_breakdown[:5]
    
    if not display_habits:
        draw.text((40, breakdown_y + 40), "— ยังไม่มีการบันทึกสถิติในช่วงเวลานี้ —", font=font_body, fill=COLOR_TEXT_SEC)
    else:
        for idx, h in enumerate(display_habits):
            item_y = breakdown_y + 40 + idx * 52
            
            # รหัสความยาวและชื่อ
            habit_label = f"{h['code']}: {h['name']}"
            if len(habit_label) > 35:
                habit_label = habit_label[:32] + "..."
                
            # วาดข้อความฝั่งซ้าย
            draw.text((40, item_y), habit_label, font=font_body, fill=COLOR_TEXT_PRI)
            
            # วาดสถิติตัวเลขฝั่งขวา
            stat_text = f"{h['count']} ครั้ง ({h['pct']}%)"
            draw.text((760 - draw.textbbox((0, 0), stat_text, font=font_body)[2], item_y), stat_text, font=font_body, fill=COLOR_TEXT_SEC)
            
            # วาดพื้นหลังแถบความก้าวหน้า (Progress Bar Track)
            track_y1 = item_y + 24
            track_y2 = item_y + 31
            draw.rounded_rectangle(
                [(40, track_y1), (760, track_y2)],
                radius=4,
                fill=COLOR_CARD
            )
            
            # วาดส่วนแถบความก้าวหน้าตามเปอร์เซ็นต์ (Progress Bar Fill)
            pct_val = max(0, min(100, h["pct"]))
            if pct_val > 0:
                fill_w = int((pct_val / 100) * 720) # 760 - 40
                draw.rounded_rectangle(
                    [(40, track_y1), (40 + fill_w, track_y2)],
                    radius=4,
                    fill=COLOR_EMERALD
                )

    # ---------------------------------------------------------
    # 4. Contribution Calendar (ตารางความสำเร็จรายวันสไตล์ GitHub)
    # ---------------------------------------------------------
    grid_y = 705
    draw.text((40, grid_y), "ปฏิทินความสำเร็จ (Contribution Calendar)", font=font_sec_title, fill=COLOR_TEXT_PRI)
    
    # วาดกรอบพาเนลพื้นหลังตารางปฏิทิน
    panel_y1 = grid_y + 35
    panel_y2 = grid_y + 220
    draw.rounded_rectangle(
        [(40, panel_y1), (760, panel_y2)],
        radius=12,
        fill=COLOR_CARD,
        outline=COLOR_BORDER,
        width=1
    )
    
    # วาดตัวย่อวันข้างปฏิทิน (แถววัน จ. พ. ศ. อา.)
    # จันทร์=0, อังคาร=1, พุธ=2, พฤหัส=3, ศุกร์=4, เสาร์=5, อาทิตย์=6
    day_labels = {0: "จ.", 2: "พ.", 4: "ศ.", 6: "อา."}
    
    # คำนวณช่วงตาราง (Contribution Map)
    sq_size = 22
    sq_gap = 5
    grid_start_x = 90
    grid_start_y = panel_y1 + 45
    
    # วาดป้ายชื่อย่อวันสัปดาห์
    for d_idx, d_name in day_labels.items():
        label_y = grid_start_y + d_idx * (sq_size + sq_gap) + 2
        draw.text((58, label_y), d_name, font=font_card_lbl, fill=COLOR_TEXT_SEC)
        
    # วาดปุ่มสี่เหลี่ยมตามปฏิทินจริงในช่วงเวลา
    # หา offset วันแรกเพื่อจัดแนว column ให้ถูกต้อง
    # ให้เริ่มเช็คจากวันแรกของช่วงเวลา
    current_d = start_date
    max_days = (end_date - start_date).days + 1
    
    # หา offset ของวันแรกเพื่อไม่ให้คอลัมน์ขยับไม่ตรงแถว (0=จันทร์, 6=อาทิตย์)
    start_offset = start_date.weekday()
    
    for day_offset in range(max_days):
        target_d = start_date + timedelta(days=day_offset)
        
        # คำนวณ column & row
        # (day_offset + start_offset) // 7 = column index
        col_idx = (day_offset + start_offset) // 7
        row_idx = target_d.weekday() # 0=จันทร์, 6=อาทิตย์
        
        # ปรับขอบไม่ให้ล้นพาเนลขวา
        if col_idx > 22: # แสดงสูงสุดได้ประมาณ 23 สัปดาห์ (~5-6 เดือน)
            continue
            
        # พิกัดกล่องวันสี่เหลี่ยม
        x1 = grid_start_x + col_idx * (sq_size + sq_gap)
        y1 = grid_start_y + row_idx * (sq_size + sq_gap)
        x2 = x1 + sq_size
        y2 = y1 + sq_size
        
        # สีตามผลงานวันนั้นๆ
        done_count = contribution_data.get(target_d, 0)
        color_fill = CONTRIBUTION_COLORS.get(min(done_count, 4), CONTRIBUTION_COLORS[0])
        
        # วาดกล่องมนขนาดเล็ก
        draw.rounded_rectangle(
            [(x1, y1), (x2, y2)],
            radius=4,
            fill=color_fill
        )
        
    # วาดคำอธิบายระดับสีตารางด้านล่าง (Legend)
    legend_x = 550
    legend_y = panel_y2 - 30
    draw.text((legend_x - 40, legend_y), "น้อย", font=font_card_lbl, fill=COLOR_TEXT_SEC)
    
    for score in range(5):
        lx1 = legend_x + score * (14 + 4)
        ly1 = legend_y + 2
        lx2 = lx1 + 14
        ly2 = ly1 + 14
        draw.rounded_rectangle(
            [(lx1, ly1), (lx2, ly2)],
            radius=3,
            fill=CONTRIBUTION_COLORS[score]
        )
        
    draw.text((legend_x + 5 * 18 + 5, legend_y), "มาก", font=font_card_lbl, fill=COLOR_TEXT_SEC)

    # ---------------------------------------------------------
    # 5. Footer Section
    # ---------------------------------------------------------
    footer_text = "Generated by My Diary Bot • Supabase Secure Cloud Storage"
    footer_w = draw.textbbox((0, 0), footer_text, font=font_footer)[2]
    draw.text(((800 - footer_w) // 2, 955), footer_text, font=font_footer, fill=COLOR_TEXT_SEC)
    
    # ส่งออกภาพออกมาเป็น Byte Buffer
    import io
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    return img_byte_arr.getvalue()

async def ensure_infographics_bucket_exists():
    """ตรวจสอบความพร้อมของถังเก็บข้อมูล 'infographics' บน Supabase หากไม่พบจะพยายามสร้างใหม่แบบเงียบๆ ไม่บล็อกตอนบูต"""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.warning(
            "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not configured! "
            "Self-healing bucket setup and Infographic Generator will not work."
        )
        return False
        
    supabase_url = supabase_url.rstrip("/")
    bucket_url = f"{supabase_url}/storage/v1/bucket"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # 1. เช็คว่ามี bucket แล้วหรือยัง
            res = await client.get(f"{bucket_url}/infographics", headers=headers, timeout=10.0)
            if res.status_code == 200:
                logger.info("Supabase storage bucket 'infographics' verified.")
                return True
                
            # 2. หากไม่พบ (404) ทำการสั่งสร้าง
            logger.info("Supabase storage bucket 'infographics' not found. Attempting to create a secure private bucket...")
            create_body = {
                "id": "infographics",
                "name": "infographics",
                "public": False, # ปลอดภัยสูงสุด: สิทธิ์แบบ Private
                "file_size_limit": 5242880, # 5MB limit
                "allowed_mime_types": ["image/png"]
            }
            try:
                create_res = await client.post(bucket_url, headers=headers, json=create_body, timeout=10.0)
                if create_res.status_code == 200:
                    logger.info("Successfully created Supabase Private storage bucket 'infographics'.")
                    return True
                else:
                    logger.warning(
                        f"Could not create storage bucket (status {create_res.status_code}): {create_res.text}. "
                        "Make sure your Supabase role has storage permission."
                    )
            except Exception as bucket_err:
                logger.warning(f"Error attempting to create storage bucket: {bucket_err}")
                
            return False
        except Exception as e:
            logger.warning(f"Exception verifying Supabase 'infographics' bucket: {e}")
            return False

async def generate_and_upload_infographic(
    user_id: str,
    period_label: str,
    period_key: str,
    stats: dict,
    habit_breakdown: list,
    contribution_data: dict,
    start_date: date,
    end_date: date
) -> str | None:
    """แกนหลักสำหรับประมวลผลวาดภาพสถิติแบบอะซิงโครนัส อัปโหลดขึ้นคลาวด์อย่างปลอดภัย และส่งกลับเป็น Signed URL"""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables are missing.")
        return None
        
    supabase_url = supabase_url.rstrip("/")
    bucket_name = "infographics"
    
    # 1. วาดรูปภาพด้วย Pillow แยกเกลียวการทำงานออกไปใน ThreadPool เพื่อไม่ให้บล็อกลูป
    async with CONCURRENCY_SEMAPHORE:
        logger.info(f"Isolating Pillow rendering in thread executor for user {user_id}...")
        loop = asyncio.get_running_loop()
        try:
            image_bytes = await loop.run_in_executor(
                THREAD_EXECUTOR,
                render_infographic_sync,
                period_label,
                stats,
                habit_breakdown,
                contribution_data,
                start_date,
                end_date
            )
        except Exception as e:
            logger.exception(f"Failed to render Pillow image: {e}")
            return None

    # 2. ตั้งชื่อไฟล์แบบคงที่ (Static) อิงตามช่วงเวลาเพื่อ overwrite รายงานของช่วงนั้นๆ ป้องกันไฟล์สะสมล้นคลาวด์
    import hashlib
    user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:12]
    filename = f"{user_hash}/summary_{period_key}.png"
    
    upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{filename}"
    upload_headers = {
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "image/png",
        "x-upsert": "true"
    }
    
    async with httpx.AsyncClient() as client:
        # 3. อัปโหลดข้อมูลไบนารี PNG ขึ้นถังเก็บข้อมูล Supabase
        logger.info(f"Uploading infographic file '{filename}' to Supabase storage...")
        try:
            upload_res = await client.post(
                upload_url,
                headers=upload_headers,
                content=image_bytes,
                timeout=30.0
            )
            if upload_res.status_code not in (200, 201):
                logger.error(f"Supabase storage upload failed: {upload_res.status_code} - {upload_res.text}")
                return None
            logger.info("Upload to Supabase Storage succeeded.")
        except Exception as e:
            logger.exception(f"Exception during Supabase file upload: {e}")
            return None
            
        # 4. ออกคีย์ความปลอดภัย Signed URL สื่อสารกลับแบบจำกัดอายุการเข้าถึง 24 ชั่วโมงเพื่อความเสถียรสูงสุด
        sign_url = f"{supabase_url}/storage/v1/object/sign/{bucket_name}/{filename}"
        sign_headers = {
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
        sign_body = {"expiresIn": 86400} # 24 ชั่วโมง
        
        logger.info(f"Generating temporary Signed URL for file '{filename}' (expiresIn: 86400s)...")
        try:
            sign_res = await client.post(
                sign_url,
                headers=sign_headers,
                json=sign_body,
                timeout=10.0
            )
            if sign_res.status_code != 200:
                logger.error(f"Supabase storage signed URL request failed: {sign_res.status_code} - {sign_res.text}")
                return None
                
            data = sign_res.json()
            signed_path = data.get("signedURL") or data.get("signedUrl")
            if not signed_path:
                logger.error(f"Response from Supabase sign request missing URL path key: {data}")
                return None
                
            # แปลงรูปแบบเส้นทางให้กลายเป็น URL ที่สมบูรณ์พร้อมยิงหา LINE
            if signed_path.startswith("/"):
                full_signed_url = f"{supabase_url}/storage/v1{signed_path}"
            else:
                full_signed_url = signed_path
                
            logger.info(f"Infographic secure signed URL ready: {full_signed_url}")
            return full_signed_url
            
        except Exception as e:
            logger.exception(f"Exception requesting signed URL: {e}")
            return None
