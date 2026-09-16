# Transit Survey Project Startup Form

Local Streamlit app for project managers to record transit survey setup details. Every **Save** writes a new Snowflake snapshot (who + when + full answers). Opening a project loads the latest version; older versions stay in History. Questionnaire and sampling-plan files go to S3.

This app is Python-only (Streamlit + HTML/CSS). It talks to Snowflake and S3 directly — no React, no separate API process.

## What you need

- Python 3.10+
- A Snowflake account, warehouse, and permission to create the `TRANSIT_SURVEY` database (or an existing database/schema you prefer)
- An S3 bucket and AWS credentials

## 1. Create the Snowflake tables

In a Snowflake worksheet, run [`sql/init.sql`](sql/init.sql). That creates:

- `TRANSIT_SURVEY.STARTUP_FORM.USERS`
- `TRANSIT_SURVEY.STARTUP_FORM.PROJECTS`
- `TRANSIT_SURVEY.STARTUP_FORM.LANGUAGES` (seeded with common languages)
- `TRANSIT_SURVEY.STARTUP_FORM.PROJECT_SNAPSHOTS` (immutable save history)

If you already have a database, change the `USE DATABASE` / `USE SCHEMA` lines and match those names in `.env`.

## 2. Configure Snowflake and S3

```powershell
copy .env.example .env
```

Edit `.env`:

```
SNOWFLAKE_ACCOUNT=xy12345.us-east-1
SNOWFLAKE_USER=your_user
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=TRANSIT_SURVEY
SNOWFLAKE_SCHEMA=STARTUP_FORM
SNOWFLAKE_ROLE=ACCOUNTADMIN
SNOWFLAKE_PRIVATE_KEY_PATH=C:\path\to\keys\rsa_key.p8
ADMIN_PASSWORD=choose-a-password

S3_BUCKET=your-bucket
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_PREFIX=startup-form
```

Use key-pair auth (`SNOWFLAKE_PRIVATE_KEY_PATH`). Password + Duo is not used.

## 3. Install and start the form

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run streamlit_app/app.py
```

If you already have the existing virtualenv, use `.\backend\.venv\Scripts\Activate.ps1` instead.

Open the URL Streamlit prints (usually http://localhost:8501).

## How to use it

1. Click **Admin** on the form and enter `ADMIN_PASSWORD` from `.env`.
2. **Admin → Saved records** — review every project's latest answers and older versions.
3. **Admin → Lists** — add users, projects, and languages.
4. **User** — pick who is filling the form (or Other + typed name). Required on every save.
5. **Project** — select one, or use **+** to create a project. The latest snapshot loads automatically.
6. Fill **Project set up info**. Weekday and weekend O-D kits are separate. If O-D or SAS is Yes, the follow-up questions appear.
7. **Save** — inserts a new Snowflake snapshot. Previous answers are not overwritten.
8. **History** — open an older save as read-only. Return to latest, edit, and Save to add another version.

Questionnaire and sampling-plan files are uploaded to the S3 bucket in `.env`. The snapshot stores an `s3://` path; opening the filename uses a time-limited download link.

## Notes

Streamlit talks to Snowflake and S3 through `lib/db.py`, `lib/storage.py`, and `lib/serializers.py`.
