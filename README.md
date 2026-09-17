# Blinded screening review

A Streamlit app for blinded, independent title-and-abstract review of an AI-screened evidence-review dataset. It supports two reviewers, conflict adjudication, lead-only comparison with AI decisions, and complete review exports.

The repository includes a screened dataset of 1,129 records and uses a reproducible 20% quality-assurance sample of 226 records by default.

## Features

- Keeps reviewers blinded to AI decisions and to each other's decisions.
- Gives both reviewers the same reproducible random sample.
- Records `Include`, `Exclude`, or `Unsure` decisions with exclusion reasons and notes.
- Locks completed reviewer submissions.
- Provides blinded adjudication of reviewer conflicts.
- Shows progress, agreement, and AI-comparison statistics to the lead.
- Exports completed reviews as CSV, RIS, or Excel.
- Runs locally with file-based storage or collaboratively with Supabase.

## Quick start

Requirements: Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_review_app.py
```

Open `http://localhost:8501` if the browser does not open automatically.

Without Supabase credentials, the app starts in local mode and stores progress in `review_app_local_state.json`. This file is intentionally excluded from Git.

## Review workflow

1. Open the app as **Lead**.
2. Use the bundled spreadsheet or upload a CSV/XLSX file containing the AI decisions.
3. Create the reproducible 20% random sample.
4. Reviewer A and Reviewer B independently screen every sampled record.
5. Each reviewer locks their review after all records have a saved decision.
6. The adjudicator resolves reviewer conflicts while remaining blinded to the AI decisions.
7. The lead examines review statistics and exports the completed dataset.

The bundled configuration uses random seed `20260914` and samples 226 of the 1,129 records.

## Shared storage with Supabase

Local storage is suitable for a demonstration on one computer. For multiple reviewers or a cloud deployment, configure Supabase so that progress persists and is shared.

1. Create a Supabase project.
2. Run [`review_database_schema.sql`](review_database_schema.sql) in the Supabase SQL editor.
3. Add these values to `.streamlit/secrets.toml` for local use, or to the app's **Secrets** settings in Streamlit Community Cloud:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your-key"
```

`SUPABASE_SERVICE_ROLE_KEY` is also supported, but it grants elevated access and should only be used when necessary. Never commit real credentials. The app hashes reviewer access codes before saving them.

## Deploy to Streamlit Community Cloud

This repository is ready to deploy from GitHub:

- Repository: `anielabankowicz-creator/blinded-screening-review`
- Branch: `main`
- Main file path: `streamlit_review_app.py`

In [Streamlit Community Cloud](https://share.streamlit.io/), create an app using those values. Add the Supabase values under **Advanced settings > Secrets** before deployment if the app will be used by multiple people.

Cloud-local files are not durable. A deployed app without Supabase may lose review progress when it restarts or redeploys.

## Project files

| File | Purpose |
| --- | --- |
| `streamlit_review_app.py` | Main Streamlit application |
| `local_review_storage.py` | Local JSON-backed storage for demonstrations |
| `supabase_review_storage.py` | Shared Supabase storage layer |
| `review_database_schema.sql` | Non-destructive database schema |
| `TASO_fin_deduplicated_1129_screened.csv` | Bundled AI-screened dataset |
| `screen_taso_financial_support.py` | Reproducible RIS screening script |
| `requirements.txt` | Python dependencies |

More detailed setup and deployment notes are available in [`REVIEW_APP_SETUP.md`](REVIEW_APP_SETUP.md) and [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Data and security notes

- Reviewer screens do not expose AI decisions, AI rationale, AI confidence, adjudications, or the other reviewer's decisions.
- The adjudicator can see reviewer decisions but remains blinded to AI decisions.
- AI decisions and comparison metrics are available only in lead mode.
- The included access-code system is designed for controlled review workflows; configure database permissions and secrets appropriately before handling sensitive data.
