import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from backend.database.connection import AsyncSessionLocal
from backend.database.models import MemberModel, PolicyModel


def money(value: Decimal | int | str) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def seed_policy_data() -> None:
    policy_path = Path(__file__).resolve().parents[2] / "assignment" / "policy_terms.json"
    if not policy_path.exists():
        return

    data = json.loads(policy_path.read_text(encoding="utf-8"))
    policy_id = data["policy_id"]
    coverage = data["coverage"]
    holder = data["policy_holder"]

    async with AsyncSessionLocal() as session:
        policy = await session.get(PolicyModel, policy_id)
        if not policy:
            policy = PolicyModel(policy_id=policy_id)
            session.add(policy)

        annual_limit = money(coverage["annual_opd_limit"])
        full_pledged = money(coverage["sum_insured_per_employee"])
        floater_limit = money(coverage["family_floater"]["combined_limit"])

        policy.policy_name = data["policy_name"]
        policy.insurer = data["insurer"]
        policy.company_name = holder["company_name"]
        policy.policy_start_date = holder["policy_start_date"]
        policy.policy_end_date = holder["policy_end_date"]
        policy.status = holder["renewal_status"]
        policy.full_pledged_amount = full_pledged
        policy.annual_opd_limit = annual_limit
        policy.remaining_opd_limit = annual_limit
        policy.family_floater_enabled = str(coverage["family_floater"]["enabled"]).lower()
        policy.family_floater_limit = floater_limit
        policy.family_floater_remaining = floater_limit

        for member_data in data["members"]:
            member = await session.get(MemberModel, member_data["member_id"])
            if not member:
                member = MemberModel(member_id=member_data["member_id"])
                session.add(member)

            ytd_claimed = Decimal(member.ytd_claimed_amount or "0.00") if getattr(member, "ytd_claimed_amount", None) else Decimal("0.00")
            remaining = max(Decimal(annual_limit) - ytd_claimed, Decimal("0.00"))

            member.policy_id = policy_id
            member.name = member_data["name"]
            member.date_of_birth = member_data["date_of_birth"]
            member.gender = member_data.get("gender")
            member.relationship = member_data["relationship"]
            member.join_date = member_data.get("join_date")
            member.primary_member_id = member_data.get("primary_member_id")
            member.full_pledged_amount = full_pledged
            member.annual_opd_limit = annual_limit
            member.ytd_claimed_amount = money(ytd_claimed)
            member.remaining_opd_limit = money(remaining)

        await session.commit()