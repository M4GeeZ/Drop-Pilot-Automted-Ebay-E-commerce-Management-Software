# DropPilot 1.1 — Vercel setup (Windows)

This package keeps the existing portal and adds a private login and a Flask Vercel entry point. Local mode still uses SQLite unless DATABASE_URL is explicitly set. Cloud mode requires persistent PostgreSQL; it never falls back to temporary SQLite.

## 1. Create a private repository
Extract the ZIP. Open the DropPilot folder (the folder containing app.py). Upload the source to a NEW private GitHub repository, or use your existing private repository after backing up the old version. Do not upload data/, .env files, google-key.json, .xlsx files or any password. The .gitignore protects these when using git; check files manually when using GitHub web upload.

## 2. Create PostgreSQL
Create a free Neon project at https://neon.com/ (select Free, not a paid plan). Copy the pooled connection string from Connect. Use SSL. In Vercel import the GitHub repository, framework Flask (or auto-detected), root directory DropPilot if your repo contains an outer folder. Leave default build/install commands. Set environment variable DATABASE_URL to the pooled connection string. Tables are created automatically on first API request. New cloud installs start with demo data. See migration below for existing local data.

## 3. Secure login
In Windows PowerShell, from the extracted folder:

    python generate_password_hash.py

Enter a new unique password (prefer a password manager; at least 12 characters). Copy the generated PBKDF2 hash, not the plaintext. Add Vercel environment variables:

- DROPPILOT_EMAIL = your intended login email address
- DROPPILOT_PASSWORD_HASH = the complete output of the script
- DATABASE_URL = your Neon connection string

Set the variables in Production (and Preview only if needed; use a separate preview database). Do not commit them. Deploy or redeploy after editing environment variables. There is no default cloud password or registration endpoint. Login sessions are random 256-bit tokens stored as hashes in PostgreSQL; failed login attempts are throttled (5 failures, 5-minute lock). Logout revokes the current token. The browser keeps the token only in memory, so closing the tab, opening a new tab, or refreshing the document requires signing in again. Browser back/forward cache restoration also prompts for login. The server token expires after eight hours; closing the tab cannot reliably notify a server, so a stolen token would remain usable until expiration or revocation. Do not share browser access or credentials. If changing credentials, clear the sessions table in Neon (`DELETE FROM sessions;`) to invalidate old sessions immediately.

## 4. Google Sheets (optional)
Enable Sheets API and create a service account in Google Cloud. Share your test spreadsheet with the service account email as Editor. Set GOOGLE_SERVICE_ACCOUNT_JSON to the entire service account JSON as a secret environment variable in Vercel. Redeploy. Create a real workspace (not demo), connect the sheet URL and tab in the portal, and click Sync now. Automatic Google sync checks the active workspace every 30 seconds while the authenticated portal remains open, respecting the configured interval. Browser background throttling and provider quotas may delay it. With the tab closed there is no continuous worker on Vercel. Use the local version for continuous local sync while your PC runs. Local Excel absolute paths cannot be accessed on Vercel; use local mode or Google Sheets/CSV online. No live marketplace provider is included.

## 5. Existing local data (optional)
The old local SQLite database is not automatically copied to Vercel. Export each workspace as CSV and import it into a new real cloud workspace; or use the migration utility for a fresh cloud database. To migrate, install dependencies (`python -m pip install -r requirements.txt`), stop the old local app, back up its data directory, set DATABASE_URL temporarily in PowerShell, and run `python migrate_local.py "C:\path\to\old\DropPilot\data\droppilot.sqlite3"`. This only works against a fresh target with no real workspaces; it replaces the seeded demo workspace. Local Excel connections are disconnected in cloud; reconnect to Google Sheets if desired. Never upload your original database to GitHub.

## 6. Local testing
`start.bat` still runs the original local HTTP server. To enable the new login locally, set DROPPILOT_EMAIL and DROPPILOT_PASSWORD_HASH as environment variables before running `python server.py --open`. Leave DATABASE_URL unset for local SQLite. The cloud Flask adapter and PostgreSQL require installed dependencies. Tests: `python -m unittest discover -s tests -v` (use an isolated local test environment, no DATABASE_URL). Cloud deployment and live database/Google API integration require your own credentials and must be smoke-tested after deployment. Vercel Hobby is subject to non-commercial personal-use eligibility and quotas; if this is company/business use, check the applicable plan terms before deploying.

## 7. Chrome extension
Reload the unpacked extension from the updated extension folder. Set the DropPilot URL to your HTTPS Vercel URL. Capture opens a new tab, so authentication is required before the captured data can be edited or published. Data capture stays in the URL fragment and is removed after import into the form.
