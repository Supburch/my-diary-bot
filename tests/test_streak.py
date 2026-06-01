import unittest
from datetime import date, timedelta

def calculate_streak(active_dates: list[date], today: date) -> tuple[int, int]:
    """คำนวณหาสถิติการทำต่อเนื่อง (Current Streak) และประวัติทำต่อเนื่องยาวนานที่สุด (Best Streak)
    จากลิสต์ของวันที่บันทึกความสำเร็จ (เฉพาะ Habit ไม่รวม Note)
    """
    if not active_dates:
        return 0, 0
        
    # กรองเอาตัวซ้ำออกและเรียงลำดับจากเก่าไปใหม่
    unique_dates = sorted(list(set(active_dates)))
    
    # 1. คำนวณ Best Streak (ทำต่อเนื่องยาวนานที่สุด)
    best_streak = 0
    temp_streak = 0
    prev_date = None
    
    for d in unique_dates:
        if prev_date is None:
            temp_streak = 1
        else:
            diff = (d - prev_date).days
            if diff == 1:
                temp_streak += 1
            elif diff > 1:
                if temp_streak > best_streak:
                    best_streak = temp_streak
                temp_streak = 1
        prev_date = d
        
    if temp_streak > best_streak:
        best_streak = temp_streak
        
    # 2. คำนวณ Current Streak (ทำต่อเนื่องปัจจุบัน)
    active_set = set(unique_dates)
    anchor = None
    
    if today in active_set:
        anchor = today
    elif (today - timedelta(days=1)) in active_set:
        anchor = today - timedelta(days=1)
        
    current_streak = 0
    if anchor is not None:
        cursor = anchor
        while cursor in active_set:
            current_streak += 1
            cursor -= timedelta(days=1)
            
    return current_streak, best_streak


class TestStreakCalculation(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 6, 1)

    def test_case_1_first_day(self):
        # Case 1: วันแรกใช้งาน (today)
        active_dates = [self.today]
        current, best = calculate_streak(active_dates, self.today)
        self.assertEqual(current, 1)
        self.assertEqual(best, 1)

    def test_case_2_three_consecutive_days(self):
        # Case 2: ติดกัน 3 วัน (today, today-1, today-2)
        active_dates = [self.today, self.today - timedelta(days=1), self.today - timedelta(days=2)]
        current, best = calculate_streak(active_dates, self.today)
        self.assertEqual(current, 3)
        self.assertEqual(best, 3)

    def test_case_3_missing_yesterday(self):
        # Case 3: ขาดเมื่อวาน (today, today-2)
        active_dates = [self.today, self.today - timedelta(days=2)]
        current, best = calculate_streak(active_dates, self.today)
        self.assertEqual(current, 1)
        self.assertEqual(best, 1)

    def test_case_4_best_greater_than_current(self):
        # Case 4: Best > Current (current: 3, best in past: 5)
        # Past: today-5 to today-9 (5 days)
        # Current: today to today-2 (3 days)
        past_streak = [self.today - timedelta(days=d) for d in range(5, 10)]
        curr_streak = [self.today - timedelta(days=d) for d in range(0, 3)]
        active_dates = curr_streak + past_streak
        current, best = calculate_streak(active_dates, self.today)
        self.assertEqual(current, 3)
        self.assertEqual(best, 5)

    def test_case_5_multiple_habits_same_day(self):
        # Case 5: หลาย Habit วันเดียว
        active_dates = [self.today, self.today, self.today]
        current, best = calculate_streak(active_dates, self.today)
        self.assertEqual(current, 1)
        self.assertEqual(best, 1)

    def test_case_6_empty_dates(self):
        # Case 6: ไม่มีข้อมูล (หรือมีแต่ Note ที่ถูกกรองออกตั้งแต่แรก)
        active_dates = []
        current, best = calculate_streak(active_dates, self.today)
        self.assertEqual(current, 0)
        self.assertEqual(best, 0)

    def test_case_7_morning_no_reset(self):
        # Case 7: ตอนเช้ายังไม่ได้บันทึก (เมื่อวานมี วันนี้ไม่มี)
        active_dates = [self.today - timedelta(days=1), self.today - timedelta(days=2)]
        current, best = calculate_streak(active_dates, self.today)
        self.assertEqual(current, 2)
        self.assertEqual(best, 2)

    def test_case_8_midnight_border(self):
        # Case 8: บันทึกคาบเกี่ยวเที่ยงคืน (05-31 23:59 -> 06-01 00:01)
        d1 = date(2026, 5, 31)
        d2 = date(2026, 6, 1)
        active_dates = [d1, d2]
        current, best = calculate_streak(active_dates, self.today)
        self.assertEqual(current, 2)
        self.assertEqual(best, 2)


if __name__ == "__main__":
    unittest.main()
