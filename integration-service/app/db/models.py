from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
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


class IntegrationTransaction(Base):
    __tablename__ = "integration_transaction"
    __table_args__ = (
        UniqueConstraint("operation_type", "external_reference", name="uq_op_ext_ref"),
        UniqueConstraint("reverses_txn_id", name="uq_one_reversal"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    loan_reference: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RWF")
    rail: Mapped[str] = mapped_column(String(64), nullable=False, default="offline")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="RECEIVED")
    reverses_txn_id: Mapped[Optional[str]] = mapped_column(ForeignKey("integration_transaction.id"), nullable=True)
    response_status: Mapped[Optional[int]] = mapped_column(nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    legs: Mapped[List["TransactionLeg"]] = relationship(back_populates="txn", cascade="all, delete-orphan")


class TransactionLeg(Base):
    __tablename__ = "transaction_leg"
    __table_args__ = (UniqueConstraint("txn_id", "leg_type", name="uq_txn_leg_type"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    txn_id: Mapped[str] = mapped_column(ForeignKey("integration_transaction.id"), nullable=False)
    leg_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_reference: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    txn: Mapped[IntegrationTransaction] = relationship(back_populates="legs")


class LoanMap(Base):
    __tablename__ = "loan_map"
    __table_args__ = (UniqueConstraint("loan_reference", name="uq_loan_reference"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    loan_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    fineract_loan_id: Mapped[int] = mapped_column(nullable=False)
    client_uid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    disbursed_txn_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("integration_transaction.id"), unique=True, nullable=True
    )


class ClientMap(Base):
    __tablename__ = "client_map"
    __table_args__ = (UniqueConstraint("client_uid", name="uq_client_uid"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    fineract_client_id: Mapped[int] = mapped_column(nullable=False)


class GlAccountMap(Base):
    __tablename__ = "gl_account_map"
    __table_args__ = (UniqueConstraint("source_system", "external_reference", name="uq_gl_source_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    fineract_gl_id: Mapped[int] = mapped_column(nullable=False)
    sync_state: Mapped[str] = mapped_column(String(32), nullable=False, default="SYNCED")


class RailCallbackInbox(Base):
    __tablename__ = "rail_callback_inbox"
    __table_args__ = (UniqueConstraint("rail", "rail_reference", name="uq_rail_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rail: Mapped[str] = mapped_column(String(64), nullable=False)
    rail_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
