from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import os, uuid, logging
from services import money, money_str, equal_shares, validate_shares, calculate_balances, calculate_settlements

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="Splitwise Lite API")
api = APIRouter(prefix="/api")

class ParticipantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)

class ExpenseCreate(BaseModel):
    description: str = Field(min_length=1, max_length=140)
    amount: str
    paid_by: str
    participant_ids: List[str]
    shares: Optional[Dict[str, str]] = None
    category: Optional[str] = "Other"

def clean_name(name):
    return " ".join(name.strip().split())

async def participant_docs():
    return await db.participants.find({}, {"_id": 0}).sort("created_at", 1).to_list(500)

async def expense_docs():
    return await db.expenses.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)

async def prepare_expense(payload: ExpenseCreate, existing_id=None):
    try: amount = money(payload.amount)
    except (InvalidOperation, ValueError): raise HTTPException(400, "Enter a valid expense amount")
    if amount <= 0: raise HTTPException(400, "Expense amount must be greater than zero")
    description = clean_name(payload.description)
    if not description: raise HTTPException(400, "Expense description is required")
    if len(set(payload.participant_ids)) != len(payload.participant_ids): raise HTTPException(400, "Participants cannot be duplicated")
    people = await db.participants.find({"id": {"$in": payload.participant_ids}}, {"_id": 0}).to_list(500)
    if len(people) != len(payload.participant_ids): raise HTTPException(400, "One or more participants were not found")
    payer = await db.participants.find_one({"id": payload.paid_by}, {"_id": 0})
    if not payer: raise HTTPException(400, "Payer was not found")
    try: shares = validate_shares(amount, payload.shares or equal_shares(amount, payload.participant_ids), payload.participant_ids)
    except ValueError as error: raise HTTPException(400, str(error))
    return {"description": description, "amount": money_str(amount), "paid_by": payload.paid_by, "participant_ids": payload.participant_ids, "shares": [{"participant_id": pid, "amount": shares[pid]} for pid in payload.participant_ids], "category": payload.category or "Other", "updated_at": datetime.now(timezone.utc).isoformat()}

@api.get("/")
async def root(): return {"message": "Expense Splitter API"}

@api.get("/participants")
async def get_participants(): return await participant_docs()

@api.post("/participants", status_code=201)
async def add_participant(payload: ParticipantCreate):
    name = clean_name(payload.name)
    if not name: raise HTTPException(400, "Participant name is required")
    duplicate = await db.participants.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
    if duplicate: raise HTTPException(400, "That participant already exists")
    doc = {"id": str(uuid.uuid4()), "name": name, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.participants.insert_one(doc)
    return {"id": doc["id"], "name": doc["name"], "created_at": doc["created_at"]}

@api.get("/expenses")
async def get_expenses():
    expenses = await expense_docs(); people = {p["id"]: p["name"] for p in await participant_docs()}
    for e in expenses:
        e["paid_by_name"] = people.get(e["paid_by"], "Unknown")
        for share in e.get("shares", []): share["participant_name"] = people.get(share["participant_id"], "Unknown")
    return expenses

@api.post("/expenses", status_code=201)
async def add_expense(payload: ExpenseCreate):
    doc = await prepare_expense(payload)
    doc.update({"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()})
    await db.expenses.insert_one(doc)
    return {key: doc[key] for key in ("id", "description", "amount", "paid_by", "participant_ids", "shares", "category", "created_at", "updated_at")}

@api.put("/expenses/{expense_id}")
async def update_expense(expense_id: str, payload: ExpenseCreate):
    if not await db.expenses.find_one({"id": expense_id}, {"_id": 0}): raise HTTPException(404, "Expense not found")
    doc = await prepare_expense(payload, expense_id)
    await db.expenses.update_one({"id": expense_id}, {"$set": doc})
    return {"id": expense_id, **doc}

@api.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str):
    result = await db.expenses.delete_one({"id": expense_id})
    if not result.deleted_count: raise HTTPException(404, "Expense not found")
    return {"message": "Expense deleted"}

@api.get("/balances")
async def get_balances():
    balances = calculate_balances(await participant_docs(), await expense_docs())
    return {"balances": balances, "settlements": calculate_settlements(balances)}

@api.get("/balances/{participant_id}/details")
async def balance_details(participant_id: str):
    people = await participant_docs(); person = next((p for p in people if p["id"] == participant_id), None)
    if not person: raise HTTPException(404, "Participant not found")
    expenses = await expense_docs(); details = []
    for e in expenses:
        paid = e["paid_by"] == participant_id
        share = next((s for s in e.get("shares", []) if s["participant_id"] == participant_id), None)
        if paid or share: details.append({"expense_id": e["id"], "description": e["description"], "paid": e["amount"] if paid else "0.00", "share": share["amount"] if share else "0.00"})
    balance = next(b for b in calculate_balances(people, expenses) if b["participant_id"] == participant_id)
    return {"participant": person, "balance": balance, "expenses": details}

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])
logging.basicConfig(level=logging.INFO)

@app.on_event("shutdown")
async def shutdown(): client.close()