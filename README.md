# AI Voice Agent Platform

Phase 4: action-taking BFSI banking assistant with LLM-driven tool calling, mock CBS integration, and audit logging.

## Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, WebSockets, MongoDB |
| Telephony | Twilio Voice + Media Streams |
| STT | Deepgram Streaming |
| LLM | Groq (with native tool/function calling) |
| TTS | ElevenLabs |
| Agent Engine | Configurable multi-agent framework |
| Tools | Banking actions (EMI, loans, callbacks, payment links, transfer) |
| Frontend | React, Vite, TypeScript |

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env           # configure credentials
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Twilio Webhooks (required for calls)

Twilio must reach your server. In development, use ngrok:

```powershell
# From project root (works even if `ngrok` is not in PATH yet)
.\start-ngrok.ps1
```

Or, after opening a **new** terminal: `ngrok http 8000`

If you see an "agent version too old" error, run `ngrok update` once, then retry.

Set `BASE_URL` in `backend/.env` to your ngrok HTTPS URL (e.g. `https://abc123.ngrok.io`), then restart the backend.

WebSocket media streams use `wss://` automatically when `BASE_URL` is HTTPS.

### Required API keys (Phase 2+)

Add to `backend/.env`:

| Variable | Description |
|----------|-------------|
| `DEEPGRAM_API_KEY` | Deepgram API key for streaming STT |
| `GROQ_API_KEY` | Groq API key for LLM responses |
| `BANK_NAME` | Bank name used in greetings (default: ABC Bank) |

## Phase 3 — BFSI Agent Engine

The platform includes a configurable agent framework for banking use cases:

- **ABC Bank EMI Reminder Agent** (seeded on startup)
- Compliance guardrails and response validation
- Objection handling library
- Escalation engine
- Conversation state machine (persisted in MongoDB)
- Analytics tracking

### Agent API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/agents` | List all agent configs |
| GET | `/agents/default` | Get default EMI Reminder Agent |
| GET | `/agents/{agent_id}` | Get agent by ID |
| POST | `/agents` | Create new agent |
| PUT | `/agents/{agent_id}` | Update agent (increments version) |
| GET | `/agents/analytics/summary` | Aggregated analytics |
| GET | `/agents/analytics/call/{call_id}` | Per-call analytics |

### Initiate call with agent context

```json
POST /calls/initiate
{
  "customer_id": "...",
  "agent_id": "",
  "agent_context": {
    "emi_amount": "Rs. 15,000",
    "due_date": "15th June 2026",
    "loan_account": "LN-123456",
    "payment_status": "overdue"
  }
}
```

If `agent_id` is empty, the default EMI Reminder Agent is used.

## Phase 4 — Tool Calling

The agent automatically invokes banking tools when customers request actions or data:

| Tool | Purpose |
|------|---------|
| `get_loan_details` | Fetch loan type, outstanding amount, EMI |
| `check_emi_due` | Check pending EMI amount, due date, status |
| `schedule_callback` | Schedule a future callback (stored in MongoDB) |
| `send_payment_link` | Send payment link via SMS (mock) |
| `transfer_to_human` | Transfer to human agent (mock) |

### Tool pipeline

```
Customer → STT → Groq (tool selection) → Tool execution → Groq (response) → TTS
```

The LLM never invents banking data — it always calls tools and uses the returned results.

### Tool API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tools` | List available tools |
| POST | `/tools/execute` | Manually execute a tool (testing) |
| GET | `/tools/logs` | Recent tool execution audit logs |
| GET | `/tools/logs/call/{call_id}` | Tool logs for a call |
| GET | `/tools/callbacks` | List scheduled callbacks |

### MongoDB collections

- `callbacks` — scheduled callback records
- `tool_execution_logs` — tool name, arguments, result, execution time

## Documentation

- Backend API: http://localhost:8000/docs
- Admin UI: http://localhost:5173

See `backend/README.md` and `frontend/README.md` for detailed setup.
