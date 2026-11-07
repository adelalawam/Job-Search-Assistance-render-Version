# Job Search Assistance — Full-stack MVP

A deployable multi-user web application starter. It includes:
- Responsive dark premium UI with 3D animated hero
- Account registration/login with hashed passwords and JWT sessions
- Separate user profiles and private CV file storage
- PDF, DOCX and TXT text extraction
- Per-user job preferences and configurable minimum match score
- Job catalogue, transparent heuristic matching and sorting
- Application tracker, duplicate protection and cover-letter draft
- Account deletion and CV deletion endpoints
- Docker and Render deployment configuration

## Important scope and honest limitations
This is a functional full-stack MVP, not a finished global autonomous job-submission service. The current release does **not** contain universal live job-board search or automatic submissions. Job boards do not offer one universal API, and automated login/submission is restricted or prohibited on many platforms. The MVP lets users add vacancies and track applications. Add only official/authorized job-feed integrations and employer application APIs. Do not bypass CAPTCHAs, access controls, or platform terms. A user should review each application and confirm submission unless an employer provides an authorized integration that expressly supports it.

Matching is a transparent keyword/overlap heuristic, not a validated AI hiring assessment. Do not inflate scores to force an 80% result. A minimum threshold filters results; it does not guarantee fit. Replace or augment the matching service with a properly evaluated semantic model before commercial launch.

Before public launch:
1. Change `SECRET_KEY`; configure production PostgreSQL.
2. Use persistent private storage (or encrypted object storage) for CVs.
3. Add email verification, password reset, rate limiting, CSRF/security headers, audit logs and abuse protection.
4. Complete GDPR notices, lawful basis, retention policy, data-processing agreements, export/deletion flows and privacy review.
5. Conduct security testing and accessibility testing.
6. Add official job-provider integrations and confirm their terms and geographic coverage.
7. Have legal counsel review EU AI Act/GDPR implications and consumer/subscription terms.

## Run locally (Windows PowerShell)
1. Install Python 3.11+.
2. Extract this ZIP.
3. In the extracted folder:
   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```
4. Edit `.env` and replace `SECRET_KEY` with a long random value.
5. Start:
   ```powershell
   uvicorn app.main:app --reload
   ```
6. Open http://127.0.0.1:8000

## Deploy from GitHub in one repository upload
1. Create a **private** GitHub repository named `Job-Search-Assistance`.
2. Extract this ZIP and upload the **contents of the folder** to the repository root (including `app/`, `requirements.txt`, `Dockerfile`, `render.yaml`, `.env.example`, `.gitignore`, and `README.md`). Do not upload a real `.env`, database, or CV.
3. Create a Render account and choose **New + → Blueprint**; connect the GitHub repository. Render reads `render.yaml`.
4. Confirm the service and persistent disk. Set/verify `SECRET_KEY` is a generated secret. Use persistent storage for user CVs. For a commercial launch, migrate SQLite to managed PostgreSQL and private object storage.
5. The service serves both the frontend and API from the same domain.

GitHub Pages alone cannot host this Python backend. The repository is the source; Render (or another Python host) runs the app.

## Structure
```text
Job-Search-Assistance/
├── app/
│   ├── main.py
│   └── static/
│       └── index.html
├── requirements.txt
├── Dockerfile
├── render.yaml
├── .env.example
├── .gitignore
└── README.md
```

## API docs
Once running, open `/docs` for interactive API documentation.
