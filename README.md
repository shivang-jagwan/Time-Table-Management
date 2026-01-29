# University Timetable Generator (Local Monorepo)

This repo contains two separate apps:

- `backend/` — FastAPI (Python) + OR-Tools (later) + Supabase Postgres (server-side only)
- `frontend/` — React + Vite + Tailwind CSS v4 dashboard

Frontend never connects directly to Supabase. It only calls the backend via HTTP.

## 1) Backend setup

Create `backend/.env` from the example:

1. Copy `backend/.env.example` to `backend/.env`
2. Fill:
   - `DATABASE_URL` (Supabase Postgres connection string)
   - `JWT_SECRET`

Run:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## 2) Frontend setup

```powershell
cd frontend
npm install
npm run dev
```

By default the frontend expects the backend at `http://localhost:8000`.

## Dev auth

Use the single button "Login as Admin". No email/password. Backend issues a JWT using `JWT_SECRET`.

## Deployment

This repo is ready to deploy as a Dockerized backend.

- Build/run backend only:
   - `docker compose up --build backend`
- Or on a platform that runs a container, point it at `backend/Dockerfile` and set env vars:
   - `DATABASE_URL`
   - `JWT_SECRET`
   - optional `FRONTEND_ORIGIN`

## Solver architecture (Jan 2026)

The timetable solver is **academic-year based** (year-only).

- Semester is not part of the domain model.
- Solve endpoints accept an academic year (and there is also a program-global solve).

If upgrading an existing DB, apply migrations from `backend/migrations/`.
