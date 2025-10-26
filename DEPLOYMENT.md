Deployment guide — Render (backend) and Vercel (frontend)

Overview
- Backend: Python FastAPI app lives in `backend/` (entrypoint `backend/main.py`). Uses Uvicorn. CORS middleware already enabled.
- Frontend: Next.js app in `frontend/`. Use Vercel for optimal Next.js support.

Local testing
- Backend (from repo root):
  cd backend
  python -m pip install -r requirements.txt
  uvicorn main:app --reload --host 0.0.0.0 --port 8000

- Frontend (from repo root):
  cd frontend
  npm install
  npm run dev

Render — deploy the backend
1) Create a new Web Service on Render
   - In Render dashboard, select "Connect a repository" and pick this repository.
   - When prompted for the root directory, set it to: `backend` (or use the included `render.yaml`).
   - Environment: Python
   - Build command: pip install -r requirements.txt
   - Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
   - Branch: main (or your chosen branch)
2) Environment variables (set in Render service settings)
   - TWILIO_ACCOUNT_SID
   - TWILIO_AUTH_TOKEN
   - TWILIO_PHONE_NUMBER
   - OPENAI_API_KEY
   - WEBHOOK_BASE_URL: set this to the public URL Render assigns to your service (e.g. https://your-backend.onrender.com)
   - (Optional) CANDIDATE_NAME, CANDIDATE_PHONE, etc.
3) Database/persistence note
   - The app uses SQLite (`conversations.db`) in the container filesystem. This is ephemeral on service redeploys.
   - For durable storage, use a managed DB (Postgres/MySQL) and update the app to use that instead of SQLite.
4) Verify
   - After deploy, open `https://<your-backend>.onrender.com/` and confirm JSON status response.

Vercel — deploy the frontend
1) Create a new Vercel project and connect the same Git repo.
   - When prompted for root directory, set it to: `frontend`.
   - Vercel auto-detects Next.js and will use `npm run build` and `npm run start`.
2) Set environment variables (Project Settings > Environment Variables)
   - NEXT_PUBLIC_API_URL = https://<your-backend>.onrender.com  # the Render backend URL
   - (Do NOT put sensitive keys here unless necessary; Twilio/OpenAI should remain in backend only.)
3) Build & preview
   - Push a commit to `main` (or the branch linked to Vercel). Vercel will run the build and deploy automatically.
   - Test that the frontend calls the backend (open the UI, check network calls, or curl NEXT_PUBLIC_API_URL)

Notes & security
- CORS: Backend already enables CORS with allow_origins=["*"]. Consider restricting to your frontend domain in production.
- Secrets: Keep Twilio and OpenAI keys only in backend env vars.
- Webhook for Twilio: Twilio needs a public webhook (WEBHOOK_BASE_URL). After Render gives your backend URL, set that value and update Twilio webhook settings.

Troubleshooting
- 500 errors: Check Render service logs and the `conversation.log` created by the backend.
- Twilio call issues: Ensure WEBHOOK_BASE_URL is HTTPS and reachable by Twilio (no localhost). Use ngrok for local testing.

Optional: Vercel rewrites/proxy
- If you prefer the frontend to proxy API calls at `/api/*`, add rewrites in `next.config.js` or use Vercel `vercel.json` to rewrite `/api` to the backend URL.

Template files
- `render.yaml` (template added at repo root). Edit the name/root/build/start fields as needed before use.

If you want, I can:
- Add a `vercel.json` with recommended rewrites for local testing (optional).
- Add a small script to the backend to auto-detect the Render URL and set it as `WEBHOOK_BASE_URL` at runtime (not recommended — set env var in Render instead).
