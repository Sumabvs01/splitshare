# Splitwise Lite

An Expense Splitter for trips and shared group spending. It keeps participant contributions, exact paise-level shares, balances, and a minimal settlement plan in one clear dashboard.

## Features

- Add and list participants with duplicate-name validation
- Add expenses with description, amount, payer, category, and selected participants
- Equal split helper with exact rounding (₹1,000 / 3 becomes ₹333.33, ₹333.33, ₹333.34)
- Unequal custom shares, validated again by the backend
- Live total spent, count, and highest-expense dashboard summary
- Balance meaning for every participant: Gets back, Needs to pay, or Settled
- Backend settlement engine minimizing debtor-to-creditor transactions
- Balance breakdown modal explaining paid amount, share, net balance, and contributing expenses
- Edit and delete expenses with automatic recalculation
- Friendly loading, empty, validation, success, and error states
- Responsive light dashboard with an optional dark view

## Technology

- React 19, React Router, Axios, Lucide icons, Tailwind-compatible CSS
- FastAPI, Pydantic, Motor
- MongoDB using the existing `MONGO_URL` and `DB_NAME` configuration

## Architecture

The backend keeps request validation in the API layer and reusable monetary/business rules in `backend/services.py`:

`React dashboard → FastAPI REST API → validation/service functions → MongoDB`

The current starter project was MongoDB-based, so the existing database technology was preserved. Expenses store a junction-style `shares` collection inside each expense document, keeping each expense and its participant shares consistent in one write. This avoids introducing a second database for a two-hour exercise while retaining the same participant/expense/share conceptual schema.

## Data model

`participants`: `id`, `name`, `created_at`

`expenses`: `id`, `description`, `amount`, `paid_by`, `participant_ids`, `category`, `shares[]`, `created_at`, `updated_at`

`expenses.shares[]`: `participant_id`, `amount`

Monetary values are stored as strings with exactly two decimal places. The service layer uses Python `Decimal`, never binary floating-point arithmetic, for validation and calculations.

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/participants` | List participants |
| POST | `/api/participants` | Add a participant |
| GET | `/api/expenses` | List expenses with display names |
| POST | `/api/expenses` | Create an expense |
| PUT | `/api/expenses/{expense_id}` | Update an expense |
| DELETE | `/api/expenses/{expense_id}` | Delete an expense |
| GET | `/api/balances` | Return balances and settlements |
| GET | `/api/balances/{participant_id}/details` | Explain one participant’s balance |

Example participant request:

```bash
curl -X POST "$REACT_APP_BACKEND_URL/api/participants" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Rahul"}'
```

Example unequal expense request:

```json
{
  "description": "Hotel",
  "amount": "5000.00",
  "paid_by": "rahul-id",
  "participant_ids": ["rahul-id", "priya-id", "amit-id", "neha-id"],
  "shares": {
    "rahul-id": "2000.00",
    "priya-id": "1500.00",
    "amit-id": "1000.00",
    "neha-id": "500.00"
  },
  "category": "Hotel"
}
```

Invalid totals return HTTP 400 with a response such as `{ "detail": "Shares must total ₹5000.00" }`.

## Balance and settlement rules

For each participant:

`net balance = total paid - total owed`

Positive values mean the participant receives money, negative values mean they need to pay. The settlement service builds debtor and creditor queues and matches the smallest remaining amount until all queues are empty.

## Running locally

1. Start MongoDB and ensure `backend/.env` contains `MONGO_URL` and `DB_NAME`.
2. Start the backend with the existing supervisor configuration on port 8001.
3. In `frontend/.env`, keep `REACT_APP_BACKEND_URL` pointed at the backend URL.
4. Run `yarn start` from `frontend/` for the React development server.
5. Run `yarn build` from `frontend/` for a production build.

## Design decisions

- MongoDB was retained because it was the existing working project stack and is available through the protected environment configuration.
- A share array acts as the expense-participant junction structure without requiring a second write or a new database dependency.
- Decimal precision is enforced by `Decimal` and two-decimal string storage.
- Balances and settlements are calculated in reusable backend services, not in React.
- Backend validation remains authoritative; frontend checks only improve the interaction.

## Assumptions and limitations

- This is a single shared trip ledger; authentication and multiple trip workspaces are intentionally out of scope.
- Deleting a participant is not offered because existing expenses should never be orphaned.
- Duplicate expense warnings are not automatic rejection; the current demo keeps the flow lightweight.
