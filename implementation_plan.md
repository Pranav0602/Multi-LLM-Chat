# Fix Railway Backend & Vercel Frontend Deployment Issues + Railway PostgreSQL Migration

Resolves the configuration mismatch and deployment errors between the FastAPI backend deployed on Railway ([multi-llm-chat-production.up.railway.app](https://multi-llm-chat-production.up.railway.app/)) and the React Vite frontend deployed on Vercel ([Multi-LLM Research Chat](https://multi-llm-chat-sandy.vercel.app/)), and provides instructions to connect the Railway backend to the PostgreSQL database in Railway project [zucchini-perception](https://railway.com/project/960679f2-62a1-49af-9fa1-54ebf3876b2c) and restore [multi-llm-chat_backup.sql](file:///d:/Python%20projects/Multi-LLM%20group%20chat/multi-llm-chat_backup.sql).

---

## Root Cause Analysis

1. **Railway Backend Returning 502 Bad Gateway**:
   - **Static Port Binding**: Both root [Dockerfile](file:///d:/Python%20projects/Multi-LLM%20group%20chat/Dockerfile) and [backend/Dockerfile](file:///d:/Python%20projects/Multi-LLM%20group%20chat/backend/Dockerfile) hardcode `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`. Railway sets a dynamic `PORT` environment variable and routes edge traffic to it. When Railway forwards to its assigned port (e.g. 8080) but Uvicorn only listens on 8000, Railway returns 502 Bad Gateway.
   - **PostgreSQL Scheme Incompatibility (`postgres://`)**: When PostgreSQL is provisioned on Railway, Railway injects `DATABASE_URL=postgres://...`. SQLAlchemy 1.4 & 2.0+ removed support for `postgres://` and throws `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres`, crashing Python immediately on startup before Uvicorn starts.
   - **Missing Railway Configuration**: No [railway.json](file:///d:/Python%20projects/Multi-LLM%20group%20chat/railway.json) exists to specify build settings, healthcheck path (`/health`), or restart policies.

2. **Vercel Frontend Returning 404 for API Requests**:
   - **Missing API Base URL**: In deployed commit `39d1ae8`, [frontend/src/api.js](file:///d:/Python%20projects/Multi-LLM%20group%20chat/frontend/src/api.js) had `const BASE = ''`. All API calls (`/groups`, `/conversations`) were made to `https://multi-llm-chat-sandy.vercel.app/groups`, which 404s because Vercel only hosts static HTML/JS.
   - **Uncommitted Changes & Placeholder Rewrites**: Untracked [frontend/vercel.json](file:///d:/Python%20projects/Multi-LLM%20group%20chat/frontend/vercel.json) contained `{ "destination": "https://YOUR-RAILWAY-URL.railway.app" }`. Furthermore, proxying long-running LLM chat turns (which can take 30-60s) through Vercel serverless rewrites hits Vercel's strict 10s-15s timeout limit. Direct client-to-Railway calls with CORS are faster and have no timeout constraints.

3. **CORS Restrictions**:
   - Backend `CORS_ORIGINS` in git did not allow `https://multi-llm-chat-sandy.vercel.app` or any Vercel preview branch deployments (`https://*.vercel.app`).
   - Changes in [backend/app/config.py](file:///d:/Python%20projects/Multi-LLM%20group%20chat/backend/app/config.py) were never staged, committed, or pushed to GitHub, meaning Railway ran old images without CORS permissions.

4. **Database Restoration Requirements**:
   - [multi-llm-chat_backup.sql](file:///d:/Python%20projects/Multi-LLM%20group%20chat/multi-llm-chat_backup.sql) begins with `PGDMP`, which indicates it is a **PostgreSQL custom-format archive (`pg_dump -Fc`)**, not plain SQL text.
   - It **must** be restored using `pg_restore` (with flags like `--no-owner --no-privileges`), not `psql < file.sql` (which will fail with syntax errors).

---

## User Review Required

> [!IMPORTANT]
> **Railway PostgreSQL Connection & Restoration**:
> 1. In your Railway project [zucchini-perception](https://railway.com/project/960679f2-62a1-49af-9fa1-54ebf3876b2c):
>    - Ensure the PostgreSQL database service is created.
>    - Under PostgreSQL service **Variables**, obtain the **Public URL / Connection URL** (e.g. `postgresql://postgres:<password>@<host>:<port>/railway` or check the TCP Proxy in Settings).
>    - In the backend service settings on Railway, link the variable: `DATABASE_URL = ${{Postgres.DATABASE_URL}}` (or set `DATABASE_URL` to the Postgres connection string).
> 2. **Restoring the backup file**:
>    - Since local Windows does not have native `pg_restore` installed, but Docker is installed (`Docker version 28.1.1`), we will run `pg_restore` via Docker directly against the Railway PostgreSQL public endpoint.
>
> **GitHub Push Requirement**:
> Railway and Vercel auto-deploy from your GitHub repository branch (`main`). After these code modifications are applied locally, you will push the commit to `origin/main` to trigger live redeployment.
>
> **Vercel Environment Variables**:
> - In Vercel Project Settings > Environment Variables, verify `VITE_API_URL` is set to `https://multi-llm-chat-production.up.railway.app`.
> - As a fail-safe, we will also configure a production default in [frontend/src/api.js](file:///d:/Python%20projects/Multi-LLM%20group%20chat/frontend/src/api.js) so it works even if the Vercel variable was not configured.

---

## Proposed Changes

### Backend & Container Configuration

#### [MODIFY] [Dockerfile](file:///d:/Python%20projects/Multi-LLM%20group%20chat/Dockerfile) & [backend/Dockerfile](file:///d:/Python%20projects/Multi-LLM%20group%20chat/backend/Dockerfile)
- Change CMD to use shell execution syntax with fallback:
  `CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]`
- Ensures dynamic `$PORT` provided by Railway (or 8000 default) is correctly bound.

#### [NEW] [railway.json](file:///d:/Python%20projects/Multi-LLM%20group%20chat/railway.json)
- Define deployment config:
  ```json
  {
    "$schema": "https://railway.com/railway.schema.json",
    "build": {
      "builder": "DOCKERFILE",
      "dockerfilePath": "Dockerfile"
    },
    "deploy": {
      "startCommand": "sh -c \"uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}\"",
      "healthcheckPath": "/health",
      "healthcheckTimeout": 100,
      "restartPolicyType": "ON_FAILURE",
      "restartPolicyMaxRetries": 5
    }
  }
  ```

#### [MODIFY] [backend/app/config.py](file:///d:/Python%20projects/Multi-LLM%20group%20chat/backend/app/config.py)
- Sanitize `DATABASE_URL`:
  - Convert `postgres://` prefix to `postgresql://` automatically for SQLAlchemy 2.0.
  - Fall back to `sqlite:///./research_chat.db` if empty.
- Update default `CORS_ORIGINS` to include:
  `"http://localhost:5173,http://localhost:3000,https://multi-llm-chat-sandy.vercel.app"`

#### [MODIFY] [backend/app/database.py](file:///d:/Python%20projects/Multi-LLM%20group%20chat/backend/app/database.py)
- Sanitize DB URL at engine instantiation to guarantee no `postgres://` dialect crash can occur regardless of input.
- Keep thread safety args for SQLite.

#### [MODIFY] [backend/alembic/env.py](file:///d:/Python%20projects/Multi-LLM%20group%20chat/backend/alembic/env.py)
- Sanitize `DATABASE_URL` so Alembic runs migrations against PostgreSQL without dialect errors.

#### [MODIFY] [backend/app/main.py](file:///d:/Python%20projects/Multi-LLM%20group%20chat/backend/app/main.py)
- Add `allow_origin_regex=r"https://.*\.vercel\.app"` to `CORSMiddleware` so Vercel preview and production deployments are always permitted.
- Add an automatic startup seed helper: if database has zero groups, seed the default "Physics Research" demo group and default CodeCraft models so the application is ready immediately if started with an empty database.

---

### Frontend Configuration

#### [MODIFY] [frontend/src/api.js](file:///d:/Python%20projects/Multi-LLM%20group%20chat/frontend/src/api.js)
- Configure robust base URL resolution:
  ```javascript
  const RAW_URL =
    import.meta.env.VITE_API_URL ||
    (import.meta.env.DEV ? '' : 'https://multi-llm-chat-production.up.railway.app');
  const BASE = RAW_URL.replace(/\/+$/, '');
  ```
  - In local dev (`npm run dev`): requests use `''` and Vite proxy (`http://localhost:8000`).
  - In production build: uses `VITE_API_URL` if set in Vercel; otherwise cleanly defaults to `https://multi-llm-chat-production.up.railway.app`.
  - Removes trailing slashes to prevent `//groups` routing issues.

#### [MODIFY] [frontend/vercel.json](file:///d:/Python%20projects/Multi-LLM%20group%20chat/frontend/vercel.json)
- Replace placeholder rewrites (`YOUR-RAILWAY-URL.railway.app`) with standard Single Page Application (SPA) routing:
  ```json
  {
    "rewrites": [
      { "source": "/(.*)", "destination": "/index.html" }
    ]
  }
  ```
- Direct API calls avoid Vercel's 10-second serverless execution limits during long LLM conversations.

---

### Railway PostgreSQL Connection & Backup Restoration

1. **Link Backend Service to Railway Postgres**:
   - In Railway project [zucchini-perception](https://railway.com/project/960679f2-62a1-49af-9fa1-54ebf3876b2c):
   - Navigate to the backend service &rarr; **Variables**.
   - Add/verify `DATABASE_URL`: `${{Postgres.DATABASE_URL}}` (or reference the Postgres service URL).

2. **Restore `multi-llm-chat_backup.sql` into Railway Postgres**:
   - Since the backup file is in PostgreSQL custom archive format (`PGDMP`), we use `pg_restore`.
   - In PowerShell, run the restore command using Docker:
     ```powershell
     # Replace <PUBLIC_DATABASE_URL> with the Railway PostgreSQL public TCP connection URL
     docker run --rm -v "${PWD}:/backup" postgres:16-alpine pg_restore -v --no-owner --no-privileges --clean --if-exists -d "<PUBLIC_DATABASE_URL>" /backup/multi-llm-chat_backup.sql
     ```
   - Flags explained:
     - `--no-owner`: Do not set ownership of objects to match the original dump user (avoids role does not exist errors on Railway).
     - `--no-privileges`: Prevents privilege assignment errors.
     - `--clean --if-exists`: Cleans existing tables before restoring data if they exist.

---

## Verification Plan

### Automated / Local Verification
1. **Frontend Build Verification**:
   - Run `npm run build` in `frontend` with and without `VITE_API_URL`.
   - Verify bundle builds with zero errors and contains the correct API endpoint.
2. **Backend Engine / Config Verification**:
   - Test Python script verifying `DATABASE_URL` sanitization for `postgres://` -> `postgresql://` and empty string fallbacks.
   - Run FastAPI lifespan startup check to verify database initialization, schema migration, and seeding.

### Post-Deployment Verification
1. **Railway Health Check**:
   - Once pushed and redeployed, fetch `https://multi-llm-chat-production.up.railway.app/health` and verify HTTP 200 `{"status": "ok", "app": "Multi-LLM Research Chat"}`.
   - Fetch `https://multi-llm-chat-production.up.railway.app/groups` to verify restored groups return HTTP 200 JSON.
2. **Vercel Frontend Verification**:
   - Open `https://multi-llm-chat-sandy.vercel.app/`.
   - Check browser developer tools: verify no CORS errors, groups load successfully, and turns can be initiated.
