# Voice Agent Admin — Frontend

React admin dashboard for the ABC Bank AI Voice Agent Platform (Phase 1).

## Features

- Create and list customers
- Trigger outbound calls per customer
- View call logs with Twilio status

## Setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

Ensure the backend is running at `http://localhost:8000` (or update `VITE_API_BASE_URL` in `.env`).

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | FastAPI backend URL |
