# AI Voice Agent Platform — Backend

Phase 2: real-time two-way conversational outbound calls using **FastAPI**, **WebSockets**, **MongoDB**, **Twilio Media Streams**, **Deepgram**, **Groq**, and **ElevenLabs**.

## Features

- Customer CRUD (create, list)
- Outbound conversational calls with Twilio Media Streams
- Real-time speech-to-text via Deepgram
- Intelligent responses via Groq LLM
- Dynamic text-to-speech via ElevenLabs (ulaw 8 kHz for telephony)
- Barge-in support (customer can interrupt AI)
- Conversation memory and transcript persistence
- Structured logging with latency metrics

## Prerequisites

- Python 3.11+
- MongoDB (local or Atlas)
- Twilio account with a voice-enabled phone number
- ElevenLabs API key and voice ID
- Deepgram API key
- Groq API key
- **Public URL** for webhooks and WebSockets (use [ngrok](https://ngrok.com/) in development)

## Setup

### 1. Create virtual environment

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `TWILIO_ACCOUNT_SID` | Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token |
| `TWILIO_PHONE_NUMBER` | Your Twilio number (E.164) |
| `ELEVENLABS_API_KEY` | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | Premade voice ID (free API: `21m00Tcm4TlvDq8ikWAM`) |
| `DEEPGRAM_API_KEY` | Deepgram API key for streaming STT |
| `GROQ_API_KEY` | Groq API key for LLM |
| `GROQ_MODEL` | Groq model (default: `llama-3.3-70b-versatile`) |
| `MONGODB_URI` | MongoDB connection string |
| `BASE_URL` | Public HTTPS URL (ngrok in dev) |
| `BANK_NAME` | Bank name for greetings (default: ABC Bank) |

### 4. Expose local server (development)

```bash
ngrok http 8000
```

Set `BASE_URL` to the ngrok HTTPS URL. WebSocket streams use `wss://` automatically.

### 5. Run the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/customers` | Create customer |
| GET | `/customers` | List customers |
| POST | `/calls/initiate` | Trigger outbound conversational call |
| GET | `/calls` | List call logs |
| GET | `/calls/{id}/transcript` | Full call transcript |
| GET | `/calls/{id}/conversation` | Conversation history with system messages |
| WS | `/ws/media-stream` | Twilio Media Streams WebSocket |
| GET | `/health` | Health check |

## Conversational Call Flow

1. Admin sends `POST /calls/initiate` with `customer_id`
2. Twilio places the outbound call
3. Customer answers → Twilio requests `/webhooks/twilio/voice/{call_id}`
4. Backend returns TwiML connecting to `wss://.../ws/media-stream?call_id=...`
5. AI greeting plays: *"Hello John. This is ABC Bank. How may I assist you today?"*
6. Customer speaks → audio streams to Deepgram STT
7. Final transcript sent to Groq → response generated
8. ElevenLabs converts response to telephony audio → streamed to customer
9. Multi-turn conversation continues until hang-up
10. Transcripts persisted to `conversation_sessions` and `transcripts` collections

## Architecture

```
Customer → Twilio Call → Media Streams → WebSocket
    → Deepgram STT → Groq LLM → ElevenLabs TTS → Customer
```

## Project Structure

```
backend/app/
├── api/
│   ├── media_stream.py      # WebSocket handler
│   ├── calls.py             # Call + transcript endpoints
│   └── webhooks.py          # Twilio webhooks
├── services/
│   ├── call_session_manager.py
│   ├── conversation_service.py
│   ├── speech_recognition_service.py
│   ├── groq_service.py
│   └── elevenlabs_service.py
├── models/conversation.py
└── utils/audio.py
```

## Performance Targets

| Stage | Target |
|-------|--------|
| STT latency | < 500 ms |
| Groq response | < 1.5 s |
| ElevenLabs TTS | < 1 s |
| End-to-end turn | < 3 s |

Latency metrics are logged on each conversation turn.
