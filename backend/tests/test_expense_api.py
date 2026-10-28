"""Regression coverage for participant, expense, balance, and validation APIs."""
import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL is required", allow_module_level=True)
BASE_URL = BASE_URL.rstrip("/")


@pytest.fixture(scope="module")
def client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def participants(client):
    response = client.get(f"{BASE_URL}/api/participants")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3
    return data[:3]


def expense_payload(participants, description="TEST_api_expense", amount="1000.00", shares=None):
    ids = [person["id"] for person in participants]
    return {
        "description": description,
        "amount": amount,
        "paid_by": ids[0],
        "participant_ids": ids,
        "shares": shares,
        "category": "Food",
    }


def test_invalid_share_total_is_rejected(client, participants):
    payload = expense_payload(participants, shares={p["id"]: "10.00" for p in participants})
    response = client.post(f"{BASE_URL}/api/expenses", json=payload)
    assert response.status_code == 400
    assert "Shares must total ₹1000.00" in response.json()["detail"]


def test_create_rounding_balances_and_delete_persistence(client, participants):
    ids = [person["id"] for person in participants]
    before_response = client.get(f"{BASE_URL}/api/balances")
    assert before_response.status_code == 200
    before = {item["participant_id"]: item for item in before_response.json()["balances"]}
    payload = expense_payload(
        participants,
        shares={ids[0]: "333.33", ids[1]: "333.33", ids[2]: "333.34"},
    )
    payload["description"] = "TEST_api_rounding"
    create = client.post(f"{BASE_URL}/api/expenses", json=payload)
    assert create.status_code == 201
    created = create.json()
    expense_id = created["id"]
    try:
        assert sorted(share["amount"] for share in created["shares"]) == ["333.33", "333.33", "333.34"]
        expenses = client.get(f"{BASE_URL}/api/expenses")
        assert expenses.status_code == 200
        persisted = next(item for item in expenses.json() if item["id"] == expense_id)
        assert persisted["description"] == "TEST_api_rounding"

        balances = client.get(f"{BASE_URL}/api/balances")
        assert balances.status_code == 200
        by_id = {item["participant_id"]: item for item in balances.json()["balances"]}
        assert float(by_id[ids[0]]["net_balance"]) - float(before[ids[0]]["net_balance"]) == 666.67
        assert float(by_id[ids[1]]["net_balance"]) - float(before[ids[1]]["net_balance"]) == -333.33
        assert float(by_id[ids[2]]["net_balance"]) - float(before[ids[2]]["net_balance"]) == -333.34
    finally:
        deleted = client.delete(f"{BASE_URL}/api/expenses/{expense_id}")
        assert deleted.status_code == 200
        remaining = client.get(f"{BASE_URL}/api/expenses")
        assert remaining.status_code == 200
        assert all(item["id"] != expense_id for item in remaining.json())