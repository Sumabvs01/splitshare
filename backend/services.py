from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, List

CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def money_str(value) -> str:
    return format(money(value), ".2f")


def equal_shares(amount, participant_ids: List[str]) -> Dict[str, str]:
    total = money(amount)
    if not participant_ids:
        return {}
    base = (total / len(participant_ids)).quantize(CENT, rounding=ROUND_DOWN)
    remainder = int((total - base * len(participant_ids)) * 100)
    return {pid: money_str(base + (CENT if index < remainder else 0)) for index, pid in enumerate(participant_ids)}


def validate_shares(amount, shares: Dict[str, str], participant_ids: List[str]):
    if not participant_ids:
        raise ValueError("Select at least one participant")
    if set(shares) != set(participant_ids):
        raise ValueError("Shares must be provided for every selected participant")
    values = [money(v) for v in shares.values()]
    if any(value < 0 for value in values):
        raise ValueError("Shares cannot be negative")
    if sum(values, Decimal("0.00")) != money(amount):
        raise ValueError(f"Shares must total ₹{money_str(amount)}")
    return {pid: money_str(shares[pid]) for pid in participant_ids}


def calculate_balances(participants, expenses):
    result = {p["id"]: {"participant_id": p["id"], "name": p["name"], "total_paid": Decimal("0"), "total_owed": Decimal("0")} for p in participants}
    for expense in expenses:
        payer = expense["paid_by"]
        if payer in result:
            result[payer]["total_paid"] += money(expense["amount"])
        for share in expense.get("shares", []):
            if share["participant_id"] in result:
                result[share["participant_id"]]["total_owed"] += money(share["amount"])
    balances = []
    for item in result.values():
        net = item["total_paid"] - item["total_owed"]
        balances.append({**item, "total_paid": money_str(item["total_paid"]), "total_owed": money_str(item["total_owed"]), "net_balance": money_str(net), "status": "gets_back" if net > 0 else "owes" if net < 0 else "settled"})
    return balances


def calculate_settlements(balances):
    debtors = [{"id": b["participant_id"], "name": b["name"], "amount": money(-Decimal(b["net_balance"]))} for b in balances if Decimal(b["net_balance"]) < 0]
    creditors = [{"id": b["participant_id"], "name": b["name"], "amount": money(Decimal(b["net_balance"]))} for b in balances if Decimal(b["net_balance"]) > 0]
    settlements = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        amount = min(debtors[i]["amount"], creditors[j]["amount"])
        if amount > 0:
            settlements.append({"from_id": debtors[i]["id"], "from_name": debtors[i]["name"], "to_id": creditors[j]["id"], "to_name": creditors[j]["name"], "amount": money_str(amount)})
        debtors[i]["amount"] -= amount
        creditors[j]["amount"] -= amount
        if debtors[i]["amount"] == 0: i += 1
        if creditors[j]["amount"] == 0: j += 1
    return settlements