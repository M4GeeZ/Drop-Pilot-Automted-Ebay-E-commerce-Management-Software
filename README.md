# DropPilot v1.0 — Local preview / MVP

A zero-additional-software-cost, local-first dropshipping research and spreadsheet automation portal. Charcoal & Amber design, dark mode, demo workspace, independent workspaces, custom dialogs and notifications. This is a functional MVP source project, not a production SaaS or live marketplace integration.

## Windows quick start

1. Extract the entire ZIP to an ordinary folder (not inside the ZIP viewer).
2. Install free Python 3.11 or newer from https://www.python.org/downloads/ if not already installed. On Windows select “Add Python to PATH”.
3. Double-click `start.bat`. The browser opens http://127.0.0.1:8765. Leave the terminal running. Press Ctrl+C to stop.
4. The demo workspace contains 8 clearly labelled fictional products. Try Add product, My products, Sheet builder, the calculator and dark mode. Create a new workspace from the top-right workspace selector before connecting an actual sheet.

Alternative PowerShell commands, from the extracted DropPilot folder:

```powershell
python --version
python server.py --open
```

If Python is available through the Windows launcher only, replace `python` with `py -3`. If port 8765 is busy, run `python server.py --port 8766 --open` and change the extension port. On macOS/Linux use `python3 server.py` and open the localhost URL.

No Node.js, Redis, PostgreSQL server, Docker, hosting, paid API, domain or credit card is required for the local demo. Python's standard library powers the HTTP server and SQLite database. The UI uses local HTML/CSS/JavaScript and SVG icons; it downloads no fonts or third-party UI scripts. The database is created automatically in `data/droppilot.sqlite3`. The runtime is deliberately bound to loopback only.

## Enable Google and Excel integrations

Double-click `setup-integrations.bat`, or run:

```powershell
python -m pip install -r requirements.txt
```

The optional dependencies are free: openpyxl and google-auth. Internet is needed to install them and to sync Google Sheets. If your Python installation rejects a global install, use a virtual environment: `python -m venv .venv`, then `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe server.py --open`.

### Google Sheets (service account)

- Create a Google Cloud project and enable Google Sheets API. This uses ordinary Sheets API quotas; do not enable unrelated paid services.
- In IAM & Admin > Service Accounts create a service account. If your organization permits JSON keys, create a JSON key and save it as `google-key.json` next to `server.py`. Alternatively set `DROPPILOT_GOOGLE_KEY` to the absolute path before starting the app.
- Share a **copy** of your spreadsheet with the service account email as Editor. Create the tab (e.g. `Products`) first. The JSON file is private: do not upload to GitHub, send in chat, or share with others.
- In DropPilot create a real workspace. In Sheet builder map the exact existing header names. In Spreadsheets select Google Sheets, enter the URL or spreadsheet ID, enter the tab name and enable automatic synchronization. Click Connect then Sync now.
- Google Workspace administrator restrictions can prevent key creation or sharing; no workaround is provided. No live Google account was connected during development, so this adapter requires verification with your account.

Official docs: https://developers.google.com/workspace/sheets/api/quickstart and https://developers.google.com/workspace/sheets/api/limits

### Local Microsoft Excel

- Use an `.xlsx` file (not `.xls`, `.xlsm`, or cloud workbook API). Enter its absolute path, for example `C:\Users\Admin\Documents\DropPilot-Test.xlsx`. The folder must already exist. A new workbook and tab are created if needed.
- Map columns first, connect, and click Sync now. Open the file to inspect the results. Save and close Excel before the next app write; Windows may lock files that are open in Excel. A sync failure is reported, not silently ignored.
- Work on a copy first, especially if the original workbook has charts, macros, external links, merged cells or unusual formatting. openpyxl may not preserve all advanced workbook features; macro-enabled files are not supported. Formula cells in mapped ranges are not overwritten, and formula-derived input cells are skipped for safety.

## Your new custom column automation

Open **Sheet builder**. Select **Add column** to map an existing field (e.g. title, Amazon price, eBay link, source seller, ROI, health score). Set its heading to the exact heading you want. Move it up/down to set export/new-sheet sequence. Select **Add custom field** for a new text, number or link field that appears in the product editor. Save mapping.

On the next successful sync, absent headers are appended, and linked/published products populate the column from the chosen source. Future published products fill all mapped cells. Existing values in the app can be edited; free-form custom fields need your input. Current physical order in existing sheets is preserved to avoid breaking formulas; column removal unmaps the field, not physically deleting the spreadsheet column. New blank sheets and CSV exports follow your configured order. A stable `_DropPilot_ID` column is created automatically; do not edit it, copy it to new rows, or remove it.

## Sync behavior and safety

One active spreadsheet per workspace (Google or Excel). Different workspaces store independent records and mappings in one local database. Do not connect the same workbook/tab under multiple aliases. New users have no password/login yet; workspace isolation is data separation, not an authentication boundary. Keep local only.

- Publishing saves locally and queues sync if auto sync is enabled. Manual sync is always available. Drafts not already linked are not exported to sheets. Rows entered directly in the sheet can be imported automatically.
- Auto sync polls at the configured interval (60 seconds by default, minimum 15 seconds); an app edit schedules the next worker pass. App and computer must remain running. It is not instantaneous; network/locking/quota delays apply.
- Editable mapped cells use a per-cell last-synchronized baseline. A single-side edit propagates. If both sides change a field differently, that field is held and a notification records the conflict. Manually align the value on both sides and retry. Derived fields are app-authoritative except existing formulas. Percent values in mapped fields should be plain numeric percentage points (e.g. 13.6, not a percent-formatted 0.136). Use consistent USD currency in this prototype.
- Linked rows deleted externally are reported, not silently re-created. Delete in app moves a product to a reversible recycle bin and retains the spreadsheet row. Use mapped workflow status for archival. Row/column hard deletion is intentionally not automated.
- Spreadsheet and DB writes cannot be a distributed atomic transaction. Google Sheets changes between the final read and write can still race; avoid simultaneous edits during sync. Excel checks file timestamps and uses atomic file replacement. Sync may temporarily delay other writes. Use backups before attaching business-critical data.
- The default fee calculator is a simplified estimate, not an actual eBay fee quote; fees, taxes, shipping, returns and category tiers vary. Enter verified rates yourself. Dashboard sums per-unit estimates, not actual realized business revenue. Sold counts are recorded research data, not automatically inferred or counted orders.

## Chrome extension

1. Open Chrome and visit `chrome://extensions`.
2. Enable Developer mode and choose Load unpacked; select the `extension` folder.
3. On a product page select the product title text if desired, click DropPilot, review the captured page URL/title, enter visible price/shipping/availability and send to the local app. Or copy the capture JSON and use Paste capture in Add product.
4. Select the correct workspace before publishing. This extension is intentionally user-initiated and does not scrape background pages, bypass site restrictions, or pretend to fetch live marketplace data. Price, shipping and availability require user confirmation. It does not require Chrome Web Store publication.

## Current capabilities and limitations

Implemented: local persistence, workspace switching, demo data, search/filter/sort/pagination, add/edit/publish/drafts/archive, bulk status/delete, recycle bin, competitor records and pricing suggestion, decimal-based server calculations, title optimizer, configurable spreadsheet mapping/custom fields, CSV import/export, local backup, Excel sync, Google Sheets API adapter, alerts from recorded changes, history, dark/light theme, local Chrome capture extension.

Not implemented: live Amazon/competitor price/shipping/availability retrieval; automatic eBay fee schedule discovery; direct eBay integration; cloud Excel Graph API; authenticated logins; paid marketplace feeds; mobile native app; production SaaS security or 24/7 monitoring. Browser capture only assists manual research. The monitoring page responds to actual stored changes, not fabricated live marketplace checks. No guaranteed performance benchmark. A large data import or long-running external sync may affect responsiveness. SQLite with WAL, indexed workspace/ASIN, paginated UI and minimal dependencies were chosen for fast local setup. A commercial version should migrate to a managed PostgreSQL or PostgreSQL deployment, proper auth, tested sync job queue, and authorized marketplace providers.

## Tests

With Python and optional Excel dependency installed:

```powershell
python -m unittest discover -s tests -v
```

Core tests cover finance, title length, workspace isolation, duplicate ASIN, Excel two-way sync/custom column backfill/conflict protection, and formula preservation. Development HTTP smoke tests covered startup, static files, state, creation, deletion and restoration. JavaScript syntax was checked. The isolated development browser blocked localhost navigation, so full browser interaction testing and visual review must be completed on your machine. Google Sheets live sync and the Chrome extension were not tested against real external accounts/sites.

## Project layout

- `server.py` — local HTTP API, SQLite storage, jobs, account separation and sync engine
- `engine.py` — financial calculations, product validation, title optimization, field registry
- `sheets.py` — Excel and Google adapters
- `static/` — responsive frontend, stylesheet, local assets
- `extension/` — unpacked Chrome research capture extension
- `tests/` — automated core tests
- `data/` — generated local data (not included in source distribution)

Start with a fresh workspace and a test spreadsheet, then make a backup from Settings before importing real data.

## Version 1.1 cloud deployment
See [DEPLOY-VERCEL.md](DEPLOY-VERCEL.md) for private login, Vercel, PostgreSQL and migration instructions. The original local workflow is retained.
