import logging
from datetime import date
from enum import Enum
from db.models import DiaryEntry
from linebot.v3.messaging import QuickReply, QuickReplyItem, MessageAction

logger = logging.getLogger(__name__)

# Enum สำหรับจำแนกหมวดหมู่สถานะเพื่อจัดทำปุ่มตอบกลับแบบ Context-Aware
class QuickReplyContext(Enum):
    HELP = "help"
    SUMMARY = "summary"
    TOGGLE = "toggle"

def get_quick_reply_habits(
    command_map: dict[str, str],
    context: QuickReplyContext,
) -> list[tuple[str, str]]:
    """เรียงลำดับความสำคัญและคัดเลือก Habit ที่เหมาะสมเพื่อนำไปสร้าง Quick Reply (Cap สูงสุดไม่เกิน LINE Limit 13)"""
    # จัดลำดับความสำคัญแบบ Context-Aware:
    # 99, 77, 66, 33, 11, 44, 55 เป็นกลุ่มยอดนิยม/ใช้บ่อย ควรจะอยู่ซ้ายสุดเพื่อให้กดง่าย
    priority_order = ["99", "77", "66", "33", "11", "44", "55", "22", "88", "00"]
    
    # ดึงเฉพาะรหัสที่มีอยู่ใน user's command_map
    available_codes = [c for c in priority_order if c in command_map]
    
    # หากผู้ใช้เพิ่มรหัสใหม่ (เช่น "01", "02") ที่ไม่อยู่ในลำดับ priority ด้านบน ให้เอามาต่อท้าย
    for c in command_map.keys():
        if c not in available_codes:
            available_codes.append(c)
            
    # คำนวณจำนวนที่แสดงได้
    # LINE Limit = 13 items
    max_items = 13
    
    if context == QuickReplyContext.TOGGLE:
        # มีปุ่ม "📊 สรุปวันนี้" เป็นตัวเด่น -> จองไว้ 1
        reserved = 1
        limit = max_items - reserved
        
        # จัดเรียงให้ปุ่ม "สรุปวันนี้" อยู่ลำดับแรก
        habits = []
        for c in available_codes[:limit]:
            icon = HABIT_ICONS.get(c, "▪")
            name = command_map[c]
            habits.append((f"{icon} {c} {name}", c))
            
        return [("📊 สรุปวันนี้", "รวม")] + habits
        
    elif context == QuickReplyContext.SUMMARY:
        # มีปุ่ม "❓ เมนู" เป็นตัวรอง -> จองไว้ 1
        reserved = 1
        limit = max_items - reserved
        
        habits = []
        for c in available_codes[:limit]:
            icon = HABIT_ICONS.get(c, "▪")
            name = command_map[c]
            habits.append((f"{icon} {c} {name}", c))
            
        return habits + [("❓ เมนู", "เมนู")]
        
    elif context == QuickReplyContext.HELP:
        # หน้าช่วยเหลือนำเสนอรหัสเรียงตามรหัสลำดับแบบดั้งเดิม (00, 11, 22... ไปเรื่อยๆ จนถึง 99) 
        # และต่อด้วย "📊 สรุปวันนี้" -> จองไว้ 1
        reserved = 1
        limit = max_items - reserved
        
        # เรียงตามลำดับรหัสดั้งเดิม (หรือลำดับคีย์ของ command_map)
        sorted_codes = sorted(list(command_map.keys()))
        
        habits = []
        for c in sorted_codes[:limit]:
            icon = HABIT_ICONS.get(c, "▪")
            name = command_map[c]
            habits.append((f"{icon} {c} {name}", c))
            
        return habits + [("📊 สรุปวันนี้", "รวม")]
        
    return []

def build_quick_reply(context: QuickReplyContext, command_map: dict[str, str]) -> QuickReply | None:
    """สร้าง QuickReply ออบเจกต์ตามแต่ละสถานการณ์การจิ้มของผู้ใช้งานเพื่อเพิ่มความสะดวกสบาย"""
    items = []
    
    actions = get_quick_reply_habits(command_map, context)
    if not actions:
        return None

    for label, text in actions:
        items.append(
            QuickReplyItem(
                action=MessageAction(label=label, text=text)
            )
        )
        
    return QuickReply(items=items)

# ไอคอน Emojis สวยๆ ประจำรหัส Habit
HABIT_ICONS = {
    "00": "💬",
    "11": "📖",
    "22": "🎥",
    "33": "💪",
    "44": "🏃",
    "55": "🚶",
    "66": "📈",
    "77": "🧘",
    "88": "🏡",
    "99": "💻",
}

def build_help_flex(command_map: dict[str, str]) -> dict:
    """สร้าง Flex Message หน้า Help Menu ในสไตล์ Zen Slate & Grid 2 คอลัมน์"""
    grid_contents = []
    keys = list(command_map.keys())
    
    # วนลูปจับคู่สร้าง Grid 2 คอลัมน์
    for i in range(0, len(keys), 2):
        row_boxes = []
        for j in range(2):
            if i + j < len(keys):
                code = keys[i + j]
                category = command_map[code]
                icon = HABIT_ICONS.get(code, "▪")
                
                box = {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#1E293B",
                    "cornerRadius": "md",
                    "paddingAll": "md",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "alignItems": "center",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"{icon}  {code}",
                                    "color": "#34D399",
                                    "weight": "bold",
                                    "size": "sm",
                                    "flex": 0
                                }
                            ]
                        },
                        {
                            "type": "text",
                            "text": category,
                            "color": "#FFFFFF",
                            "size": "xs",
                            "weight": "bold",
                            "margin": "xs"
                        }
                    ],
                    "flex": 1
                }
                row_boxes.append(box)
            else:
                row_boxes.append({"type": "box", "layout": "vertical", "flex": 1})
        
        grid_contents.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "md",
            "contents": row_boxes
        })

    bubble = {
        "type": "bubble",
        "size": "giga",
        "styles": {
            "header": {"backgroundColor": "#0F172A"},
            "body": {"backgroundColor": "#0F172A"}
        },
        "header": {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "contents": [
                {
                    "type": "text",
                    "text": "📋 HABIT TRACKER CODES",
                    "color": "#34D399",
                    "weight": "bold",
                    "size": "sm",
                    "letterSpacing": "0.1em"
                },
                {
                    "type": "text",
                    "text": "คีย์รหัสตัวเลข 2 หลักเพื่อลงรายการประจำวัน",
                    "color": "#94A3B8",
                    "size": "xs"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "md",
                    "contents": grid_contents
                },
                {
                    "type": "separator",
                    "color": "#1E293B"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "text",
                            "text": "💡 วิธีบันทึกโน้ตส่วนตัว (Free Note) : พิมพ์  ***ตามด้วยข้อความสั้นๆที่ต้องการบันทึก",
                            "color": "#94A3B8",
                            "size": "xs",
                            "wrap": True
                        },
                        {
                            "type": "text",
                            "text": "📊 วิธีดูสรุปประวัติรวมที่ผ่านมา: พิมพ์คำว่า รวม หรือคำว่า สรุป",
                            "color": "#94A3B8",
                            "size": "xs",
                            "wrap": True
                        }
                    ]
                }
            ]
        }
    }
    
    # สร้างข้อความสำหรับ Fallback ข้อความธรรมดา
    fallback_lines = ["📋 Habit Tracker Codes\n"]
    for code, category in command_map.items():
        fallback_lines.append(f"{code} = {category}")
    fallback_lines.append("\n***ข้อความ = บันทึก note\nรวม = สรุปวันนี้\nเมนู = ดูรายการคำสั่งและรหัส")
    
    return {
        "type": "flex",
        "alt_text": "📋 รายการรหัส Habit",
        "contents": bubble,
        "fallback_text": "\n".join(fallback_lines),
        "quick_reply": build_quick_reply(QuickReplyContext.HELP, command_map)
    }

def build_toggle_flex(code: str, category: str, is_done: bool, done_count: int, total_habits: int, command_map: dict[str, str], current_streak: int = 0) -> dict:
    """สร้าง Flex Message การ์ดตอบรับด่วนเวลาผู้ใช้สั่ง Toggle"""
    percentage = int((done_count / total_habits) * 100)
    icon = HABIT_ICONS.get(code, "▪")
    
    action_text = "บันทึกความสำเร็จ!" if is_done else "ยกเลิกบันทึกแล้ว"
    action_color = "#34D399" if is_done else "#EF4444"
    mark_symbol = "✓" if is_done else "↩️"
    
    # [P1 COMPATIBILITY CHECK] ป้องกันปัญหาการพล็อต width: 0% บนบาง LINE Client โดยใช้แถบว่างแทนถ้ายังไม่มี progress
    inner_bar = []
    if percentage > 0:
        inner_bar.append({
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#34D399",
            "height": "6px",
            "cornerRadius": "md",
            "width": f"{percentage}%",
            "contents": []
        })
    
    bubble = {
        "type": "bubble",
        "size": "mega",
        "styles": {
            "body": {"backgroundColor": "#0F172A"}
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "alignItems": "center",
                    "spacing": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": mark_symbol,
                            "color": action_color,
                            "size": "lg",
                            "weight": "bold",
                            "flex": 0
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"{icon} {code} {category}",
                                    "color": "#FFFFFF",
                                    "weight": "bold",
                                    "size": "sm"
                                },
                                {
                                    "type": "text",
                                    "text": action_text,
                                    "color": action_color,
                                    "size": "xs",
                                    "weight": "bold"
                                }
                            ],
                            "flex": 1
                        }
                    ]
                },
                {
                    "type": "separator",
                    "color": "#1E293B"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"สำเร็จแล้ว {done_count}/{total_habits}" + (f" | 🔥 ต่อเนื่อง {current_streak} วัน" if current_streak > 0 else ""),
                                    "color": "#94A3B8",
                                    "size": "xs"
                                },
                                {
                                    "type": "text",
                                    "text": f"{percentage}%",
                                    "color": "#34D399",
                                    "size": "xs",
                                    "align": "end",
                                    "weight": "bold"
                                }
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#334155",
                            "height": "6px",
                            "cornerRadius": "md",
                            "margin": "xs",
                            "contents": inner_bar
                        }
                    ]
                }
            ]
        }
    }
    
    fallback_text = f"{mark_symbol} {code} {category} | {action_text} (รวมวันนี้: {done_count}/{total_habits})"
    
    return {
        "type": "flex",
        "alt_text": "📝 อัปเดตความสำเร็จ Habit",
        "contents": bubble,
        "fallback_text": fallback_text,
        "quick_reply": build_quick_reply(QuickReplyContext.TOGGLE, command_map)
    }

def build_summary_flex(entries: list[DiaryEntry], target_date: date, command_map: dict[str, str], current_streak: int = 0, best_streak: int = 0) -> dict:
    """สร้าง Flex Message หน้าสรุปคะแนนประจำวันพร้อมเกจความคืบหน้าและกล่อง Reflection"""
    habit_map = {e.code: e for e in entries if not e.code.startswith("~~")}
    
    done_count = 0
    list_contents = []
    
    # สำหรับข้อความ Fallback
    symbol = "●" if target_date.day % 2 == 0 else "■"
    outline = "○" if symbol == "●" else "□"
    fallback_lines = [
        f"📅 {target_date}" + (f" | 🔥 ทำต่อเนื่อง {current_streak} วัน (สูงสุด {best_streak} วัน)" if current_streak > 0 else ""),
        "─" * 24
    ]
    
    for code, category in command_map.items():
        entry = habit_map.get(code)
        is_done = bool(entry and entry.done)
        
        icon = HABIT_ICONS.get(code, "▪")
        
        if is_done:
            done_count += 1
            mark_color = "#34D399"
            mark_text = "✓"
            text_color = "#FFFFFF"
            weight_str = "bold"
            extra_details = []
            
            if entry.count:
                extra_details.append(f"×{entry.count}")
            if entry.note:
                extra_details.append(entry.note)
                
            extra_text = f" ({', '.join(extra_details)})" if extra_details else ""
            
            # บันทึกใส่ fallback
            fallback_extra = ""
            if entry.count:
                fallback_extra += f" ×{entry.count}"
            if entry.note:
                fallback_extra += f" | {entry.note}"
            fallback_lines.append(f"{symbol} {code} {category}{fallback_extra}")
        else:
            mark_color = "#475569"
            mark_text = "○"
            text_color = "#64748B"
            weight_str = "regular"
            extra_text = ""
            
            # บันทึกใส่ fallback
            fallback_lines.append(f"{outline} {code} {category}")

        row = {
            "type": "box",
            "layout": "horizontal",
            "alignItems": "center",
            "spacing": "md",
            "paddingTop": "xs",
            "paddingBottom": "xs",
            "contents": [
                {
                    "type": "text",
                    "text": mark_text,
                    "color": mark_color,
                    "weight": "bold",
                    "size": "sm",
                    "flex": 0
                },
                {
                    "type": "text",
                    "text": f"{icon}  {code}  {category}{extra_text}",
                    "color": text_color,
                    "size": "xs",
                    "weight": weight_str,
                    "flex": 1,
                    "wrap": True
                }
            ]
        }
        list_contents.append(row)

    total_habits = len(command_map)
    percentage = int((done_count / total_habits) * 100)
    
    # [P1 COMPATIBILITY CHECK] ป้องกันปัญหาการพล็อต width: 0% สำหรับแถบเปอร์เซ็นต์ในหน้าสรุปรายวัน
    inner_summary_bar = []
    if percentage > 0:
        inner_summary_bar.append({
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#34D399",
            "height": "6px",
            "cornerRadius": "md",
            "width": f"{percentage}%",
            "contents": []
        })

    notes = [e.note for e in entries if e.code.startswith("~~") and e.note]
    
    body_contents = [
        {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"สำเร็จประจำวัน {done_count} / {total_habits} รายการ",
                            "color": "#E2E8F0",
                            "size": "xs",
                            "weight": "bold"
                        },
                        {
                            "type": "text",
                            "text": f"{percentage}%",
                            "color": "#34D399",
                            "size": "xs",
                            "weight": "bold",
                            "align": "end"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#334155",
                    "height": "6px",
                    "cornerRadius": "md",
                    "margin": "xs",
                    "contents": inner_summary_bar
                }
            ]
        },
        {
            "type": "separator",
            "color": "#1E293B",
            "margin": "md"
        },
        {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "margin": "md",
            "contents": list_contents
        }
    ]
    
    if notes:
        note_rows = []
        fallback_lines.append("─" * 24)
        fallback_lines.append("📝 บันทึกวันนี้:")
        for idx, n in enumerate(notes, 1):
            note_rows.append({
                "type": "text",
                "text": f"• {n}",
                "color": "#E2E8F0",
                "size": "xs",
                "wrap": True,
                "margin": "xs"
            })
            fallback_lines.append(f"  {idx}. {n}")
            
        body_contents.append({
            "type": "separator",
            "color": "#1E293B",
            "margin": "md"
        })
        body_contents.append({
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1E293B",
            "borderColor": "#F59E0B",
            "borderWidth": "1px",
            "cornerRadius": "md",
            "paddingAll": "md",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "📝 DAILY REFLECTIONS",
                    "color": "#F59E0B",
                    "weight": "bold",
                    "size": "xs",
                    "letterSpacing": "0.1em"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xs",
                    "contents": note_rows
                }
            ]
        })

    fallback_lines.append("─" * 24)
    fallback_lines.append(f"✅ {done_count}/{total_habits}")

    bubble = {
        "type": "bubble",
        "size": "giga",
        "styles": {
            "header": {"backgroundColor": "#0F172A"},
            "body": {"backgroundColor": "#0F172A"}
        },
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "📅 DAILY DIARY",
                    "color": "#94A3B8",
                    "weight": "bold",
                    "size": "xs",
                    "letterSpacing": "0.1em"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "alignItems": "center",
                    "margin": "xs",
                    "contents": [
                        {
                            "type": "text",
                            "text": target_date.strftime("%A, %d %B %Y"),
                            "color": "#FFFFFF",
                            "weight": "bold",
                            "size": "sm",
                            "flex": 1
                        },
                        {
                            "type": "text",
                            "text": f"🔥 {current_streak} วัน (สูงสุด {best_streak})" if current_streak > 0 else f"🔥 {current_streak} วัน",
                            "color": "#F59E0B",
                            "weight": "bold",
                            "size": "xs",
                            "align": "end",
                            "flex": 0
                        }
                    ]
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": body_contents
        }
    }
    
    return {
        "type": "flex",
        "alt_text": "📅 สรุปประวัติไดอารี่ประจำวัน",
        "contents": bubble,
        "fallback_text": "\n".join(fallback_lines),
        "quick_reply": build_quick_reply(QuickReplyContext.SUMMARY, command_map)
    }


def build_period_summary_flex(
    period_name: str,
    start_date: date,
    end_date: date,
    stats: dict,
    command_map: dict[str, str]
) -> dict:
    """สร้าง Flex Message การ์ดรายงานสรุปสถิติประจำช่วงเวลา (Weekly/Monthly Summary) ดีไซน์หรู Zen Slate"""
    completion_rate = stats["completion_rate"]
    current_streak = stats["current_streak"]
    longest_streak = stats["longest_streak"]
    total_checkmarks = stats["total_checkmarks"]
    top_habit_name = stats["top_habit_name"]
    top_habit_freq = stats["top_habit_freq"]
    
    # Progress Bar ด้านใน
    inner_bar = []
    if completion_rate > 0:
        inner_bar.append({
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#34D399",
            "height": "6px",
            "cornerRadius": "md",
            "width": f"{completion_rate}%",
            "contents": []
        })

    bubble = {
        "type": "bubble",
        "size": "giga",
        "styles": {
            "header": {"backgroundColor": "#0F172A"},
            "body": {"backgroundColor": "#0F172A"}
        },
        "header": {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "contents": [
                {
                    "type": "text",
                    "text": f"📋 {period_name.upper()} REPORT",
                    "color": "#34D399",
                    "weight": "bold",
                    "size": "xs",
                    "letterSpacing": "0.1em"
                },
                {
                    "type": "text",
                    "text": f"{start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "sm",
                    "margin": "xs"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                # 📈 Completion Rate Progress Bar
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "อัตราการรักษาวินัยช่วงสัปดาห์" if "WEEK" in period_name.upper() else "อัตราการรักษาวินัยช่วงเดือน",
                                    "color": "#E2E8F0",
                                    "size": "xs",
                                    "weight": "bold"
                                },
                                {
                                    "type": "text",
                                    "text": f"{completion_rate}%",
                                    "color": "#34D399",
                                    "size": "xs",
                                    "weight": "bold",
                                    "align": "end"
                                }
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#334155",
                            "height": "6px",
                            "cornerRadius": "md",
                            "margin": "xs",
                            "contents": inner_bar
                        }
                    ]
                },
                {
                    "type": "separator",
                    "color": "#1E293B",
                    "margin": "md"
                },
                # 📊 Grid items
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "md",
                    "contents": [
                        # Row 1: Streaks
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "spacing": "md",
                            "contents": [
                                {
                                    "type": "box",
                                    "layout": "vertical",
                                    "backgroundColor": "#1E293B",
                                    "cornerRadius": "md",
                                    "paddingAll": "md",
                                    "flex": 1,
                                    "contents": [
                                        {"type": "text", "text": "🔥 ทำต่อเนื่อง", "color": "#94A3B8", "size": "xxs", "weight": "bold"},
                                        {"type": "text", "text": f"{current_streak} วัน", "color": "#F59E0B", "size": "md", "weight": "bold", "margin": "xs"}
                                    ]
                                },
                                {
                                    "type": "box",
                                    "layout": "vertical",
                                    "backgroundColor": "#1E293B",
                                    "cornerRadius": "md",
                                    "paddingAll": "md",
                                    "flex": 1,
                                    "contents": [
                                        {"type": "text", "text": "🏆 สถิติสูงสุด", "color": "#94A3B8", "size": "xxs", "weight": "bold"},
                                        {"type": "text", "text": f"{longest_streak} วัน", "color": "#FFFFFF", "size": "md", "weight": "bold", "margin": "xs"}
                                    ]
                                }
                            ]
                        },
                        # Row 2: Total checkmarks & Top Habit
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "spacing": "md",
                            "contents": [
                                {
                                    "type": "box",
                                    "layout": "vertical",
                                    "backgroundColor": "#1E293B",
                                    "cornerRadius": "md",
                                    "paddingAll": "md",
                                    "flex": 1,
                                    "contents": [
                                        {"type": "text", "text": "✅ บันทึกวินัยรวม", "color": "#94A3B8", "size": "xxs", "weight": "bold"},
                                        {"type": "text", "text": f"{total_checkmarks} ครั้ง", "color": "#34D399", "size": "md", "weight": "bold", "margin": "xs"}
                                    ]
                                },
                                {
                                    "type": "box",
                                    "layout": "vertical",
                                    "backgroundColor": "#1E293B",
                                    "cornerRadius": "md",
                                    "paddingAll": "md",
                                    "flex": 1,
                                    "contents": [
                                        {"type": "text", "text": "🥇 นิสัยยอดนิยม", "color": "#94A3B8", "size": "xxs", "weight": "bold"},
                                        {"type": "text", "text": f"{top_habit_name}" + (f" ({top_habit_freq} ครั้ง)" if top_habit_freq > 0 else ""), "color": "#FFFFFF", "size": "xs", "weight": "bold", "margin": "xs", "wrap": True}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }
    
    fallback_text = (
        f"📊 รายงานสรุปสถิติ {period_name}\n"
        f"📅 ช่วงเวลา: {start_date} ถึง {end_date}\n"
        f"────────────────────────\n"
        f"📈 อัตราการรักษาวินัย: {completion_rate}%\n"
        f"🔥 ทำต่อเนื่องปัจจุบัน: {current_streak} วัน\n"
        f"🏆 สถิติสูงสุดตลอดกาล: {longest_streak} วัน\n"
        f"✅ บันทึกวินัยรวม: {total_checkmarks} ครั้ง\n"
        f"🥇 นิสัยยอดนิยม: {top_habit_name} ({top_habit_freq} ครั้ง)\n"
        f"────────────────────────"
    )
    
    return {
        "type": "flex",
        "alt_text": f"📊 รายงานสรุปสถิติ {period_name}",
        "contents": bubble,
        "fallback_text": fallback_text,
        "quick_reply": build_quick_reply(QuickReplyContext.SUMMARY, command_map)
    }
