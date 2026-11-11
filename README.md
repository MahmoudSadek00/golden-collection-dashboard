# Golden Collection Dashboard

Operations intelligence for Customer Support (Logistics to follow), built with Streamlit.

## Pages
| Section | Page | Purpose |
|---|---|---|
| Overview | Executive Overview | Score vs target, change vs comparison period, what needs attention |
| Customer Support | Performance | Team KPIs, agent scorecard, KPI breakdown, weekly/monthly trends |
| | Teams & Groups | Day-shift vs night-shift groups, change vs previous, volume contribution |
| | Agent Profile | One agent vs target, team and history; score composition; observations |
| | Period Comparison | Any two periods (month, quarter, year, week, custom), team / group / agent changes |
| | Operations | Chat and call demand, service levels, adherence, occupancy, shrinkage |
| Logistics | Logistics | Coming soon (no figures until the daily logistics data is approved) |
| Reports & Exports | Report Builder | Excel management report for the current filters |
| | Data Health | Source coverage, data issues, reconciliation with LS_Scorecard |

## Calculation rules
* Scorecard KPIs: a line-by-line port of the approved `LookerKPI.gs` engine (the script that writes LS_Scorecard /
  LS_Team). The Data Health page recalculates every LS_Scorecard value and confirms they match.
* Targets and points come from `KPI_Targets`; agents in the score from `KPI_Agents`; QA from `QA_Input`.
* The KPI score is shown only for months and quarters. 2026 Q3 scores come from `KPI_Frozen_Q3`.
* KPIs that need working days (score, chats per day, calls per day, absence) are withheld when the schedule
  (CS_Agent_Daily) is missing for the period, instead of being overstated.
* Operational metrics use the CS Pulse / Looker definitions.

## Deploy on Streamlit Cloud
1. Create a Google Cloud project, enable **Google Sheets API** and **Google Drive API**, create a **service account**
   and download its JSON key.
2. Share the Customer Support spreadsheet and *Orders - Clean Data* with the service-account e-mail (Viewer).
3. Push this folder to a private GitHub repository (the `.gitignore` keeps secrets and data out).
4. On share.streamlit.io: New app → choose the repository → main file `app.py` → Python 3.12.
5. App → Settings → Secrets: paste the content of `.streamlit/secrets.toml.example` with your real key values.
6. Set the app's sharing to private and invite the viewers who should see it.

Data is cached for one hour; the Data Health page has a "Refresh data now" button.

## Run locally
```
pip install -r requirements.txt
GC_DATA_DIR=/path/to/csv/folder streamlit run app.py     # CSV files named like the tabs, e.g. CS_Chats.csv
# or put the secrets in .streamlit/secrets.toml and run: streamlit run app.py
```

## Project structure
All files are at the top level (so the repository can be uploaded by drag-and-drop):
`app.py` (navigation), `config.py`, `data_loader.py`, `prepare.py`, `kpi_engine.py` (approved engine – do not change
without approval), `analytics.py`, `periods.py`, `comparison.py`, `insights.py`, `kpis.py`, `excel_report.py`,
`theme.py`, `components.py`, `charts.py`, `filters.py`, `state.py`, page modules (`executive.py`, `cs_*.py`,
`logistics.py`, `reports.py`, `data_health.py`, `common.py`) and `schema.py` (Logistics contract).
`.streamlit/config.toml` holds the light theme.

## Adding Logistics later
Create the daily logistics tab, add its IDs to the secrets, add `logistics_kpis.py` with the approved definitions
and replace `logistics.py` with the real pages. Nothing in the Customer Support code needs to change.
