# Setup and Deployment Guide

This guide covers the local Windows setup first, then optional Docker deployment. The application is designed for a **single self-hosted workspace**. It is not a multi-tenant public SaaS application.

## 1. Requirements

- Windows 10/11, macOS, or Linux.
- Python 3.11 or newer.
- Node.js 20 or newer and npm 10 or newer.
- A SQLAlchemy-supported database connection for the backend to reach.
- Internet access for the first dependency installation.
- Gemini API key is optional for fallback questions. Standard supported questions run locally without an LLM key.
- OpenAI API key is not required.

## 2. Windows local installation

Extract the ZIP and open the `natural-language-bi-assistant` directory in VS Code.

Open PowerShell at the project root and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

If PowerShell blocks activation, use Command Prompt instead:

```bat
.venv\Scripts\activate.bat
```

Keep the `.env` defaults initially:

```text
ENABLE_LLM_FALLBACK=false
USE_LLM_ANSWER=false
```

This keeps the supported query patterns deterministic and avoids unnecessary Gemini quota usage. To enable optional Gemini fallback later, set `GEMINI_API_KEY` and `ENABLE_LLM_FALLBACK=true` in `backend/.env`.

### Start the backend

Open terminal 1:

```powershell
cd backend
uvicorn app:app --reload
```

Verify:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

### Start the frontend

Open terminal 2 at the project root:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL, normally `http://localhost:5173`.

## 3. Connect a local SQL database

In the UI, select **Manage database**, choose a database type, paste a SQLAlchemy connection URL, and click **Test & connect**. The backend verifies the connection and discovers every accessible table/view in the active/default schema before switching to it. It reads column types, primary keys, foreign keys, and relationship paths.

### SQLite

The backend must be able to read the file. Example Windows URL:

```text
sqlite:///C:/Users/your-name/Documents/databases/sales.db
```

Example macOS/Linux URL:

```text
sqlite:////home/your-name/data/sales.db
```

The external SQLite database is opened read-only by the application.

### PostgreSQL

```text
postgresql+psycopg://readonly_user:URL_ENCODED_PASSWORD@localhost:5432/sales_db
```

Use a database role with only the required `CONNECT`, schema `USAGE`, and table `SELECT` permissions. Install requirements from `backend/requirements.txt`; the `psycopg` driver is included.

### MySQL

```text
mysql+pymysql://readonly_user:URL_ENCODED_PASSWORD@127.0.0.1:3306/sales_db
```

Use a MySQL account with `SELECT` permissions only. The `PyMySQL` driver is included in requirements.

Encode reserved characters in passwords before placing them in a URL. Examples: `@` → `%40`, `/` → `%2F`, `#` → `%23`.

### Important: what “local database” means

A connection is opened by the **backend process**, not by the browser. When running FastAPI directly on your Windows PC, it can access database files and database servers reachable from that PC. If you run the backend on a remote server, it cannot open a file that exists only on your personal PC. For that case, run the backend locally, copy/mount the database into the backend host, or use a secured private network/VPN route to a database server. Do not expose database ports to the public internet just to make them reachable.

The UI connection is held in backend memory and is not written to browser storage or returned by the API. It remains active until the backend restarts. To persist a default connection, put `DATABASE_URL=...` in `backend/.env` and protect that file.

### After connecting: database knowledge and table exploration

1. The backend introspects all accessible tables/views in the active/default schema.
2. It records every table's columns, types, nullability, primary keys, and declared foreign keys.
3. It builds a relationship graph from declared foreign keys. For databases without declared foreign keys, it only infers a shared-key relationship when the same key column occurs in multiple tables and one matching column is a primary key.
4. The assistant considers numeric measures and categorical/date dimensions across the full catalog. It can join a fact table to a related dimension table (for example, `generation_raw.SiteKey` to `solar_site_details.SiteKey` to group solar generation by `SiteName`).
5. It reads a bounded set of text-category values from eligible columns to support filters. It does not copy or load every record into memory or into an LLM prompt.
6. Open **Explore all tables** in the sidebar to see the complete catalog. Expand a table and select **Preview 5 rows** to inspect a small read-only sample from that table.

The assistant refuses a cross-table question when it cannot discover a safe relationship path. If the database uses differently named join keys and has no declared foreign keys, define the FK in the database or add a reviewed relationship mapping rather than expecting the assistant to guess.

## 4. Chart support and expected query patterns

Try these questions in the UI:

| Question | Expected result |
|---|---|
| Which city generated the highest revenue? | KPI/ranking |
| What are the top 4 cities with highest revenue? | Bar chart, up to four existing cities |
| What is the total revenue generated by each city? | Bar chart |
| Generate a bar chart for revenue by city | Bar chart |
| Generate a line chart for revenue over time | Line chart using a date/time field |
| Generate a pie chart for revenue by city | Pie chart for non-negative values |
| Show a histogram of revenue | Histogram of raw numeric observations |
| Show me 10 rows of the dataset | Data table |
| Which Solar Site generates the most solar energy? | Site-level ranking across related generation and site tables |
| What are the top 4 solar sites with highest performance? | Ranked site metric with a discovered relationship join |
| Generate a bar chart for solar generation by site | Bar chart |
| Generate a line chart of solar energy over time | Line chart by discovered date/time column |
| Generate a pie chart for solar generation by site | Pie chart when values are non-negative |
| Show a histogram of solar energy | Histogram of raw numeric observations |
| Give me all rows from performance_results | Bounded table result from the specifically named table |
| Read all the tables in the database | Database catalog listing every discovered table/view |

The result panel has a chart-type selector. It only offers chart types compatible with the returned columns and values. Pie charts are not offered for negative or non-positive totals. Histograms need a numeric measure; line charts need at least two observations to draw a line.

## 5. Docker deployment

Docker Compose is optional. It builds the FastAPI backend and a production React bundle served by Nginx.

1. Install Docker Desktop and start it.
2. From the project root, copy the Compose environment example:

```powershell
Copy-Item .env.docker.example .env
```

3. Build and start:

```powershell
docker compose up --build -d
```

4. Open `http://localhost:8080`.
5. Inspect logs:

```powershell
docker compose logs -f backend
docker compose logs -f frontend
```

6. Stop:

```powershell
docker compose down
```

### Connect databases from Docker

- **SQLite:** put the `.db` file in the project `db-files/` folder. Docker mounts it read-only at `/db-files`. Use `sqlite:////db-files/your-database.db` in the UI.
- **PostgreSQL/MySQL on the host:** use `host.docker.internal` as the hostname from the container and configure the DB server/firewall to allow only the required backend host/container network. Use a read-only DB account.
- **Remote DB:** use a private DNS/IP, TLS, and VPN/private networking. Avoid public database exposure.

## 6. Tests

With the Python virtual environment active, from the project root:

```powershell
python -m pytest
```

To run the small benchmark:

```powershell
cd backend
python run_evaluation.py
```

Unit tests mock external LLM calls and do not need Gemini or OpenAI credentials.

## 7. Troubleshooting

- **Failed to fetch:** verify FastAPI is running at `127.0.0.1:8000`; check `frontend/.env` if the API URL was changed.
- **CORS:** add the exact frontend origin to `CORS_ORIGINS` in `backend/.env`, then restart FastAPI.
- **SQLite file not found:** use an absolute path and check the backend process has read access.
- **PostgreSQL/MySQL driver error:** activate the project virtual environment and reinstall `python -m pip install -r backend\requirements.txt`.
- **No tables found:** verify the selected DB/schema and account permissions.
- **Metric not understood:** open Database Explorer and inspect numeric columns. Add a business alias/definition if the column's physical name is generic (for example `Value`).
- **Cross-table question not understood:** inspect the discovered relationships. Cross-table analytics need a declared FK or a safe shared-key relationship; arbitrary joins are intentionally not guessed.
- **Chart not visible:** check the selected visualization spec and confirm the result contains the required numeric/category/date columns. Line charts need at least two observations; pie charts need non-negative values with a positive total.
- **Table preview error:** confirm the connected database user has SELECT permission on the selected table/view.
- **Gemini quota or 503:** keep `ENABLE_LLM_FALLBACK=false` for supported patterns; deterministic query patterns do not need Gemini.

## 8. Deployment security scope

This version is designed for a private, single-workspace self-hosted deployment or controlled internal demo. It has one process-wide active database connection and in-memory conversation sessions. Before exposing it as a public multi-user service, add authentication and authorisation, per-user connection/session isolation, a secret manager, HTTPS, access logging, query timeouts, and a security review. Do not run it as an anonymous public service with permission to change database connections.
