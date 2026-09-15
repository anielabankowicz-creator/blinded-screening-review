# Deployment

## Supabase

1. Open `review_database_schema.sql` and run it in the Supabase SQL editor.
2. Add deployment secrets:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
3. Keep `.streamlit/secrets.toml` out of Git. Use `.streamlit/secrets.example.toml` as the template.

The app uses Supabase automatically when those secrets are present. If they are absent, it falls back to local demo storage.

## Streamlit deployment

Deploy `streamlit_review_app.py` as the app entrypoint with `requirements.txt`.

For Streamlit Community Cloud:

1. Push this repository to GitHub.
2. Create a new Streamlit app from that repository.
3. Set the main file path to `streamlit_review_app.py`.
4. Add the Supabase values in app secrets.
5. Deploy.
