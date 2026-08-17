from datetime import date
from sqlalchemy import Boolean, Date, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass


class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    code: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(255))
    done: Mapped[bool] = mapped_column(Boolean, default=True)
    count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)


class UserHabit(Base):
    __tablename__ = "user_habits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    code: Mapped[str] = mapped_column(String(2))
    category: Mapped[str] = mapped_column(String(255))
    icon: Mapped[str] = mapped_column(String(10), default="▪")
