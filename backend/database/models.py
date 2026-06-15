from sqlalchemy import Column, String, Integer, Float, ForeignKey, Text
from sqlalchemy.orm import relationship as orm_relationship
from .connection import Base


class PolicyModel(Base):
    __tablename__ = "policies"

    policy_id = Column(String, primary_key=True)
    policy_name = Column(String, nullable=False)
    insurer = Column(String, nullable=False)
    company_name = Column(String, nullable=False)
    policy_start_date = Column(String, nullable=False)
    policy_end_date = Column(String, nullable=False)
    status = Column(String, nullable=False)
    full_pledged_amount = Column(String, nullable=False)
    annual_opd_limit = Column(String, nullable=False)
    remaining_opd_limit = Column(String, nullable=False)
    family_floater_enabled = Column(String, nullable=False, default="false")
    family_floater_limit = Column(String, nullable=True)
    family_floater_remaining = Column(String, nullable=True)

    members = orm_relationship("MemberModel", back_populates="policy")
    claims = orm_relationship("ClaimModel", back_populates="policy")


class MemberModel(Base):
    __tablename__ = "members"

    member_id = Column(String, primary_key=True)
    policy_id = Column(String, ForeignKey("policies.policy_id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    date_of_birth = Column(String, nullable=False)
    gender = Column(String, nullable=True)
    relationship = Column(String, nullable=False)
    join_date = Column(String, nullable=True)
    primary_member_id = Column(String, ForeignKey("members.member_id"), nullable=True, index=True)
    full_pledged_amount = Column(String, nullable=False)
    annual_opd_limit = Column(String, nullable=False)
    ytd_claimed_amount = Column(String, nullable=False, default="0.00")
    remaining_opd_limit = Column(String, nullable=False)

    policy = orm_relationship("PolicyModel", back_populates="members")
    primary_member = orm_relationship("MemberModel", remote_side=[member_id], backref="dependents")
    claims = orm_relationship("ClaimModel", back_populates="member")

class ClaimModel(Base):
    __tablename__ = "claims"

    claim_id = Column(String, primary_key=True)
    member_id = Column(String, ForeignKey("members.member_id"), nullable=False, index=True)
    policy_id = Column(String, ForeignKey("policies.policy_id"), nullable=False, index=True)
    claim_category = Column(String, nullable=False)
    treatment_date = Column(String, nullable=False)
    submission_date = Column(String, nullable=False)
    claimed_amount = Column(String, nullable=False)
    hospital_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="PENDING")
    current_stage = Column(String, nullable=True)
    trace_id = Column(String, nullable=False)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    spans = orm_relationship(
        "TraceSpanModel",
        back_populates="claim",
        order_by="TraceSpanModel.started_at",
        cascade="all, delete-orphan",
    )
    decision = orm_relationship(
        "ClaimDecisionModel",
        back_populates="claim",
        uselist=False,
        cascade="all, delete-orphan",
    )
    gating_error = orm_relationship(
        "GatingErrorModel",
        back_populates="claim",
        uselist=False,
        cascade="all, delete-orphan",
    )
    member = orm_relationship("MemberModel", back_populates="claims")
    policy = orm_relationship("PolicyModel", back_populates="claims")

class TraceSpanModel(Base):
    __tablename__ = "trace_spans"

    span_id = Column(String, primary_key=True)
    claim_id = Column(String, ForeignKey("claims.claim_id"), nullable=False, index=True)
    agent_name = Column(String, nullable=False)
    stage_order = Column(Integer, nullable=False)
    started_at = Column(String, nullable=False)
    ended_at = Column(String, nullable=True)
    elapsed_ms = Column(Integer, nullable=True)
    status = Column(String, nullable=False)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    confidence_delta = Column(Float, nullable=True)
    errors = Column(Text, nullable=True)
    model_used = Column(String, nullable=True)

    claim = orm_relationship("ClaimModel", back_populates="spans")

class ClaimDecisionModel(Base):
    __tablename__ = "claim_decisions"

    claim_id = Column(String, ForeignKey("claims.claim_id"), primary_key=True)
    decision = Column(String, nullable=False)
    approved_amount = Column(String, nullable=False)
    copay_deducted = Column(String, nullable=False, default="0")
    network_discount_applied = Column(String, nullable=False, default="0")
    rejection_reasons = Column(Text, nullable=True)
    partial_items = Column(Text, nullable=True)
    member_message = Column(Text, nullable=False)
    ops_summary = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=False)
    manual_review_note = Column(Text, nullable=True)
    decided_at = Column(String, nullable=False)

    claim = orm_relationship("ClaimModel", back_populates="decision")

class GatingErrorModel(Base):
    __tablename__ = "gating_errors"

    claim_id = Column(String, ForeignKey("claims.claim_id"), primary_key=True)
    error_code = Column(String, nullable=False)
    human_message = Column(Text, nullable=False)
    detail = Column(Text, nullable=False)
    occurred_at = Column(String, nullable=False)

    claim = orm_relationship("ClaimModel", back_populates="gating_error")
