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

def build_quick_reply(context: QuickReplyContext) -> QuickReply | None:
    """สร้าง QuickReply ออบเจกต์ตามแต่ละสถานการณ์การจิ้มของผู้ใช้งานเพื่อเพิ่มความสะดวกสบาย"""
    items = []
    
    if context == QuickReplyContext.TOGGLE:
        # บันทึกความสำเร็จเรียบร้อย -> เน้นให้ดูสรุปผลลัพธ์เป็นอันดับหนึ่ง ตามด้วย Habit ที่ใช้บ่อยมาก (จัดลำดับไม่ให้ล้น scroll blindspot)
        actions = [
            ("📊 สรุปวันนี้", "sum"),
            ("💻 99 AI Coding", "99"),
            ("🧘 77 Mindfulness", "77"),
            ("📖 11 5min Read", "11"),
            ("💪 33 PU @ 10", "33"),
        ]
    elif context == QuickReplyContext.SUMMARY:
        # ผู้ใช้กำลังดู Dashboard สรุปความก้าวหน้า -> เน้นปุ่ม Habit ยอดนิยมเพื่อดึงดูดใจให้จิ้มบันทึกรายการอื่นๆ ต่อ
        actions = [
            ("💻 99 AI Coding", "99"),
            ("📈 66 Trade/Invest", "66"),
            ("🧘 77 Mindfulness", "77"),
            ("🏃 44 Squad @ 35", "44"),
            ("🚶 55 Walk 2Km", "55"),
            ("💪 33 PU @ 10", "33"),
            ("❓ ช่วยเหลือ", "help"),
        ]
    elif context == QuickReplyContext.HELP:
        # ผู้ใช้กำลังศึกษาคำสั่งคีย์ -> แสดงรหัส Habit ครบถ้วนเป็นระเบียบตามลำดับ
        actions = [
            ("💬 00 News/Talk", "00"),
            ("📖 11 5min Read", "11"),
            ("🎥 22 Documentary", "22"),
            ("💪 33 PU @ 10", "33"),
            ("🏃 44 Squad @ 35", "44"),
            ("🚶 55 Walk 2Km", "55"),
            ("📈 66 Trade/Invest", "66"),
            ("🧘 77 Mindfulness", "77"),
            ("🏡 88 Farm/House", "88"),
            ("💻 99 AI Coding", "99"),
            ("📊 สรุปวันนี้", "sum"),
        ]
    else:
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
                    "text": "ส่งรหัสตัวเลข 2 หลักเพื่อ Toggle ความสำเร็จประจำวัน",
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
                            "text": "💡 วิธีบันทึกโน้ตส่วนตัว (Free Note): พิมพ์ ~ข้อความที่ต้องการบันทึก",
                            "color": "#94A3B8",
                            "size": "xs",
                            "wrap": True
                        },
                        {
                            "type": "text",
                            "text": "📊 วิธีดูสรุปประวัติ: พิมพ์ sum หรือวันนี้",
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
    fallback_lines.append("\n~ข้อความ = บันทึก note\nsum = สรุปวันนี้")
    
    return {
        "type": "flex",
        "alt_text": "📋 รายการรหัส Habit",
        "contents": bubble,
        "fallback_text": "\n".join(fallback_lines),
        "quick_reply": build_quick_reply(QuickReplyContext.HELP)
    }

def build_toggle_flex(code: str, category: str, is_done: bool, done_count: int, total_habits: int) -> dict:
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
            "width": f"{percentage}%"
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
                                    "text": f"วันนี้สำเร็จแล้ว {done_count}/{total_habits}",
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
        "quick_reply": build_quick_reply(QuickReplyContext.TOGGLE)
    }

def build_summary_flex(entries: list[DiaryEntry], target_date: date, command_map: dict[str, str]) -> dict:
    """สร้าง Flex Message หน้าสรุปคะแนนประจำวันพร้อมเกจความคืบหน้าและกล่อง Reflection"""
    habit_map = {e.code: e for e in entries if not e.code.startswith("~~")}
    
    done_count = 0
    list_contents = []
    
    # สำหรับข้อความ Fallback
    symbol = "●" if target_date.day % 2 == 0 else "■"
    outline = "○" if symbol == "●" else "□"
    fallback_lines = [
        f"📅 {target_date}",
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
            "width": f"{percentage}%"
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
                    "text": f"📅 DAILY DIARY",
                    "color": "#94A3B8",
                    "weight": "bold",
                    "size": "xs",
                    "letterSpacing": "0.1em"
                },
                {
                    "type": "text",
                    "text": target_date.strftime("%A, %d %B %Y"),
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
            "contents": body_contents
        }
    }
    
    return {
        "type": "flex",
        "alt_text": "📅 สรุปประวัติไดอารี่ประจำวัน",
        "contents": bubble,
        "fallback_text": "\n".join(fallback_lines),
        "quick_reply": build_quick_reply(QuickReplyContext.SUMMARY)
    }
