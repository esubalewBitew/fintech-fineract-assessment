from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (
        UniqueConstraint("external_reference", name="uq_account_external_reference"),
        UniqueConstraint("code", name="uq_account_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    usage: Mapped[str] = mapped_column(String(32), nullable=False, default="DETAIL")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RWF")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manual_entries_allowed: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JournalEntry(Base):
    __tablename__ = "journal_entry"
    __table_args__ = (UniqueConstraint("external_reference", name="uq_journal_external_reference"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False, default="integration")
    reverses_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entry.id"), unique=True, nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[List["JournalLine"]] = relationship(back_populates="entry", cascade="all, delete-orphan")
    reverses: Mapped[Optional["JournalEntry"]] = relationship(remote_side="JournalEntry.id")


class JournalLine(Base):
    __tablename__ = "journal_line"
    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_line_nonneg"),
        CheckConstraint(
            "(debit = 0 AND credit > 0) OR (credit = 0 AND debit > 0)",
            name="ck_line_one_side",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entry.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship()


class FaultConfig(Base):
    __tablename__ = "fault_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(64), nullable=False, default="none")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
