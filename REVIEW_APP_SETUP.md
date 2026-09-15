# Blinded Review App Setup

## What exists in this project

- `screen_taso_financial_support.py` parses a RIS file and creates AI/rule screening decisions.
- `TASO_fin_deduplicated_1129_screened.csv` contains 1,129 screened records.
- No prior Streamlit app, Supabase module, database schema, or review-storage logic was present in the editable project.

## New files

- `streamlit_review_app.py` is the Streamlit app for blinded screening, adjudication, lead-only AI comparison, and exports.
- `supabase_review_storage.py` contains the Supabase data-access layer.
- `review_database_schema.sql` creates new review tables without dropping or altering existing data.
- `requirements.txt` lists the app dependencies.

## Safe database setup

1. Review `review_database_schema.sql`.
2. Run it in the Supabase SQL editor.
3. Configure credentials with environment variables or Streamlit secrets:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY` or `SUPABASE_SERVICE_ROLE_KEY`
4. Install dependencies:
   - `pip install -r requirements.txt`
5. Start the app:
   - `streamlit run streamlit_review_app.py`

## Blinding model

- Reviewer mode shows bibliographic data only.
- Reviewer mode does not show AI decisions, AI rationale, AI confidence, adjudication, or the other reviewer decision.
- Adjudicator mode shows reviewer decisions for blinded adjudication, but does not show AI decisions.
- Lead mode is the only place where AI decisions and comparison metrics are shown.

## Workflow

1. A lead signs in and imports the default CSV or uploads CSV/RIS/Excel.
2. The lead creates the reproducible random sample. Defaults are seed `20260914` and sample size `226`.
3. The lead creates separate reviewer, adjudicator, and lead access codes.
4. Two reviewers independently screen the same sampled records and lock their submissions.
5. The adjudicator resolves conflicts while still blinded to AI.
6. The lead reviews reviewer-reviewer and reviewer-AI agreement, kappa, confusion matrices, AI recall, specificity, predictive values, and false-exclusion rate.
7. The lead exports complete CSV, RIS, or Excel outputs.
