# AI Voice Agent Platform

Phase 7: Human handoff with escalation engine, transfer queue, and conversation context preservation.

Phase 8: Compliance & Audit layer with AI disclosure, consent tracking, and full regulatory traceability.

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
| CRM | Internal MongoDB (summaries, outcomes, lead status, campaigns) |
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

## Phase 5 — Internal CRM

After every call, the platform automatically:

- Generates conversation summaries (Groq)
- Classifies lead status and call outcome
- Extracts follow-up dates and creates callbacks
- Stores all data in MongoDB (no external CRM)

### Internal CRM API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/crm/summary/{call_id}` | Conversation summary |
| GET | `/crm/outcome/{call_id}` | Call outcome classification |
| GET | `/crm/status/{call_id}` | Lead status update |
| GET | `/crm/analytics/summary` | CRM analytics |

### MongoDB collections (Phase 5)

- `conversation_summaries` — AI-generated call summaries
- `lead_status_updates` — lead status classifications
- `call_outcomes` — call outcome records

## Phase 6 — Campaign Engine

Large-scale outbound calling from uploaded CSV datasets. Campaign execution runs in background asyncio tasks (Redis/Celery-ready architecture).

### Campaign workflow

```
Admin → Upload CSV → Create Campaign → Start Campaign
    → Campaign Queue → Batch Outbound Calls → AI Voice Agent
    → Call Results → MongoDB
```

### CSV format

```csv
Name,Phone,LoanID
John Doe,+919876543210,LN001
Raj Kumar,+919876543211,LN002
```

### Campaign API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/campaigns/create` | Create a new campaign |
| POST | `/campaigns/upload` | Upload CSV (form: `file`, `campaign_id`) |
| POST | `/campaigns/{id}/start` | Start outbound calling |
| POST | `/campaigns/{id}/pause` | Pause a running campaign |
| POST | `/campaigns/{id}/resume` | Resume a paused campaign |
| POST | `/campaigns/{id}/stop` | Stop a campaign |
| GET | `/campaigns` | List all campaigns |
| GET | `/campaigns/{id}` | Get campaign details |
| GET | `/campaigns/{id}/analytics` | Campaign analytics |
| GET | `/campaigns/{id}/customers` | List campaign customers |
| GET | `/campaigns/{id}/results` | Call results with summaries |

### Campaign configuration

Set in `backend/.env`:

| Variable | Description |
|----------|-------------|
| `CAMPAIGN_BATCH_SIZE` | Concurrent calls per batch (default: 10) |
| `CAMPAIGN_CALL_INTERVAL_SECONDS` | Delay between batch cycles (default: 5.0) |
| `CAMPAIGN_MAX_CONCURRENT_CALLS` | Max concurrent calls cap (default: 50) |

### MongoDB collections (Phase 6)

- `campaigns` — campaign metadata and status
- `campaign_customers` — imported customers per campaign
- `campaign_runs` — execution run records
- `campaign_analytics` — aggregated campaign metrics

## Phase 7 — Human Handoff

The AI detects escalation triggers, records escalations, packages conversation context, and queues transfers to human agents. Live Twilio transfer is mocked; architecture supports real `<Dial>` / SIP integration later.

### Escalation flow

```
Customer message → EscalationService + SentimentService
    → Record escalation → Transfer queue → Mock transfer
    → Preserve transcript & context → End AI handling
```

### Escalation categories

| Category | Examples |
|----------|----------|
| `CUSTOMER_REQUESTED_HUMAN` | "Speak to a person", "Transfer me to support" |
| `COMPLAINT` | "File a complaint", "This service is terrible" |
| `LEGAL_QUERY` | Legal department, lawyer, lawsuit |
| `ACCOUNT_DISPUTE` | Wrong EMI, incorrect loan info |
| `NEGATIVE_SENTIMENT` | Anger, repeated refusal, aggressive language |
| `HIGH_RISK_QUERY` | Fraud, identity theft, unauthorized transactions |

### Transfer priority

| Priority | Categories |
|----------|------------|
| HIGH | Legal, fraud/high-risk, account disputes |
| MEDIUM | Complaints, negative sentiment |
| LOW | General human requests |

### Handoff API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/escalations` | List all escalations |
| GET | `/escalations/{id}` | Get escalation by ID |
| GET | `/escalations/analytics/summary` | Escalation & transfer analytics |
| GET | `/handoff-queue` | List transfer queue items |
| GET | `/handoff-queue/{id}` | Get queue item with context |

### MongoDB collections (Phase 7)

- `escalations` — call_sid, customer_id, escalation_type, reason
- `human_handoff_logs` — transfer status and timestamp
- `transfer_queue` — priority, status, conversation context
- `handoff_context` — full context package for human agents

### Configuration

| Variable | Description |
|----------|-------------|
| `HUMAN_AGENT_PHONE` | Destination for future live transfer (E.164) |
| `HANDOFF_ENABLED` | Enable handoff pipeline (default: true) |

## Phase 8 — Compliance & Audit

Every call is fully traceable for BFSI regulatory requirements. The compliance middleware runs before conversation processing and automatically logs all events via the `AuditService`.

### Call flow

```
Customer → Voice Agent → Compliance Middleware → Conversation Processing → Audit Logger → MongoDB
```

### At call start

1. **AI disclosure** — configurable text (default: "I am an AI-powered virtual assistant calling on behalf of ABC Bank.")
2. **Consent capture** — customer must grant permission to continue
3. If consent denied → call ends gracefully

### Compliance API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/compliance/call/{call_sid}` | Full compliance package for a call |
| GET | `/compliance/transcript/{call_sid}` | Consolidated transcript |
| GET | `/compliance/audit/{call_sid}` | Compliance event audit trail |
| GET | `/compliance/consent/{call_sid}` | Consent record |
| GET | `/compliance/tool-history/{call_sid}` | Tool execution audit history |
| GET | `/compliance/dashboard/summary` | Dashboard metrics |
| GET | `/compliance/retention-policy` | Retention policy framework |

### MongoDB collections (Phase 8)

- `disclosures` — AI disclosure proof (text, played_at)
- `consents` — CONSENT_GRANTED / CONSENT_DENIED / NO_RESPONSE
- `call_recordings` — recording metadata (URL references, not audio blobs)
- `compliance_transcripts` — consolidated messages array per call
- `prompt_versions` — exact prompts used by agents
- `call_prompt_usage` — prompt version linked to each call
- `tool_audit_logs` — every tool execution with arguments and results
- `crm_audit_logs` — all internal CRM updates
- `escalation_audit_logs` — escalation history
- `compliance_events` — source-of-truth event stream

### Configuration

| Variable | Description |
|----------|-------------|
| `COMPLIANCE_ENABLED` | Enable compliance middleware (default: true) |
| `COMPLIANCE_DISCLOSURE_TEMPLATE` | AI disclosure text (`{bank_name}` placeholder) |
| `COMPLIANCE_CONSENT_PROMPT` | Consent question played after disclosure |
| `COMPLIANCE_RECORDING_NOTICE` | Optional recording notice appended to disclosure |
| `COMPLIANCE_RETENTION_*_DAYS` | Retention windows (~2555 days = 7 years). Deletion not implemented. |

## Phase F1 — Admin Portal

Full React admin UI with 10 modules wired to FastAPI:

| Module | Route | Features |
|--------|-------|----------|
| Dashboard | `/` | KPI cards, success rate chart, recent activity |
| Customers | `/customers` | CRUD, search, call history |
| Campaigns | `/campaigns` | Create, CSV upload, start/pause/resume/stop |
| Agents | `/agents` | EMI, Collections, Loan, Insurance, Support — prompt, voice, language, tools |
| Live Calls | `/live-calls` | Real-time active sessions (3s refresh) |
| Call History | `/call-history` | Transcript, recording, summary, outcome, tool calls |
| Escalations | `/escalations` | Transfer queue + escalation log |
| Compliance | `/compliance` | Consent, disclosure, audit trail, tool history |
| Analytics | `/analytics` | Success/callback/escalation rates, campaign & agent charts |
| Settings | `/settings` | Twilio/Groq/ElevenLabs status, voices, languages, campaign & compliance config |

### New Admin API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/dashboard` | Unified dashboard metrics |
| GET/PUT | `/admin/settings` | Platform settings (mutable non-secrets) |
| GET | `/calls/active` | Live call sessions |
| GET | `/calls/{call_id}` | Single call record |
| GET/PUT/DELETE | `/customers/{id}` | Customer CRUD |
| GET | `/customers/{id}/calls` | Customer call history |

## Documentation

- Backend API: http://localhost:8000/docs
- Admin UI: http://localhost:5173

See `backend/README.md` and `frontend/README.md` for detailed setup.
