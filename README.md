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
   - `JWT_SECRET_KEY`
   - `FRONTEND_ORIGIN` (e.g. `http://localhost:5173` in dev)

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

## Auth

Authentication is **username + password**. Backend sets an HttpOnly cookie (`access_token`) on login.

- Login endpoint: `POST /api/auth/login`
- Current user: `GET /api/auth/me`
- Logout endpoint: `POST /api/auth/logout`

## Deployment

This repo is ready to deploy as a Dockerized backend.

- Build/run backend only:
   - `docker compose up --build backend`
- Or on a platform that runs a container, point it at `backend/Dockerfile` and set env vars:
   - `DATABASE_URL`
   - `JWT_SECRET_KEY`
   - `ENVIRONMENT=production`
   - `FRONTEND_ORIGIN` (your frontend origin; required for CORS in production)

## Solver architecture (Jan 2026)

The timetable solver is **academic-year based** (year-only).

- Semester is not part of the domain model.
- Solve endpoints accept an academic year (and there is also a program-global solve).

If upgrading an existing DB, apply migrations from `backend/migrations/`.

## Render (recommended)

This repo includes `render.yaml` to deploy both backend + frontend on Render.

### 1) Create services from blueprint

- In Render: **New** → **Blueprint** → select this repo.
- Render will create:
   - `timetable-backend` (Python web service)
   - `timetable-frontend` (static site)

### 2) Set backend env vars (Render dashboard)

In the `timetable-backend` service → **Environment**:

- `DATABASE_URL` = your Postgres URL (Supabase or Render Postgres)
- `JWT_SECRET_KEY` = long random secret
- `FRONTEND_ORIGIN` = your frontend origin (example: `https://timetable-frontend.onrender.com` or your custom domain)
   - Note: do not include a trailing `/` (example: `https://example.com`, not `https://example.com/`)

Optional (only if frontend+backend are on different “sites” / different eTLD+1):

- `COOKIE_SAMESITE=none`

### 3) Set frontend env vars (Render dashboard)

In the `timetable-frontend` static site → **Environment**:

- `VITE_API_BASE` = your backend base URL (example: `https://timetable-backend.onrender.com`)

### 4) Verify

- Backend health: `https://<backend>/health` should show `{ "app": "ok", "database": "ok" }`
- Frontend: open `https://<frontend>` and login.

## Vercel (frontend) + Render (backend)

This setup is recommended if you want Vercel for the dashboard and Render for the API.

### Why the Vercel proxy matters (cookies + CORS)

Auth uses an HttpOnly cookie (`access_token`). If your frontend and backend are on different domains, browsers treat that cookie as third‑party and it can be blocked or require extra SameSite/CORS settings.

To avoid that, this repo includes a Vercel rewrite so the browser talks to Vercel at `/api/*`, and Vercel proxies to Render. That makes auth cookies first‑party on your Vercel domain.

### 1) Deploy backend on Render

- Create a Render **Web Service** from `backend/`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Set env vars in Render:
   - `ENVIRONMENT=production`
   - `DATABASE_URL=...`
   - `JWT_SECRET_KEY=...`
   - `SEED_ADMIN_USERNAME=...` (one-time bootstrap; create your initial admin)
   - `SEED_ADMIN_PASSWORD=...`
   - `ALLOW_SIGNUP=false` (recommended)
   - `COOKIE_SAMESITE=lax` (works with the Vercel proxy)

### 2) Configure frontend proxy (Vercel)

Edit `frontend/vercel.json` and replace:

- `https://RENDER_BACKEND_URL` with your real backend URL, for example:
   - `https://timetable-backend.onrender.com`

### 3) Deploy frontend on Vercel

- In Vercel, import the repo and set **Root Directory** = `frontend`
- Framework: Vite (auto-detected)
- Build command: `npm run build`
- Output directory: `dist`

No `VITE_API_BASE` is required when using the Vercel rewrite (the app calls `/api/...`).

### 4) Verify

- Open your Vercel URL.
- Login/signup should set cookies and load admin routes without CORS errors.







