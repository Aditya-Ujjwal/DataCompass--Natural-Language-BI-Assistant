# Natural Language BI Assistant

A self-hosted, full-stack natural-language business intelligence assistant. Ask questions about a SQL database in plain English and receive a database-backed answer, a chart, the returned rows, generated SQL, an analysis trace, and request metrics.

This release extends the earlier learning MVP with runtime SQL database connections, schema discovery, SQLite/PostgreSQL/MySQL dialect-aware SQL generation, bar/line/pie/histogram visualizations, a database connection panel, and a production-style responsive React interface.

> **Deployment scope:** this is a self-hosted, single-workspace deployment suitable for local use, demos, and a controlled internal pilot. It is not a multi-tenant public SaaS. Do not expose it directly to the public internet with access to private databases until authentication, per-user connection isolation, secret management, audit controls, and deployment-specific security review have been added.

## Quick documentation

- Detailed installation and deployment steps: [SETUP-AND-DEPLOYMENT.md](SETUP-AND-DEPLOYMENT.md)
- Checks run for this release: [VERIFICATION-REPORT.md](VERIFICATION-REPORT.md)
- SolarPulse-specific questions and expected analysis: [SOLARPULSE-TEST-QUESTIONS.md](SOLARPULSE-TEST-QUESTIONS.md)

## Features

### Database connections

- Bundled SQLite sample database for first launch.
- Connect an existing SQLite database file from the UI.
- Connect PostgreSQL with `psycopg`.
- Connect MySQL with `PyMySQL`.
- Connection test and full catalog discovery before activating a new data source.
- Introspects every accessible table/view in the selected database's active/default schema, including columns, SQL data types, nullability, primary keys, and foreign keys.
- Builds a relationship graph from declared foreign keys and conservative shared-key inference (a matching key where one side is the primary key).
- The assistant examines numeric and categorical columns across all discovered tables and uses bounded categorical-value samples for matching user filters. It does not load the entire database into model prompts.
- Database Explorer lists all discovered tables and relationships; users can explicitly preview up to five rows from any table.
- Credentials are not returned by the API and the connection URL entered in the UI is held in backend process memory only. It is not saved in browser storage or written to a project file.
- External SQLite connections are opened read-only. For PostgreSQL/MySQL, use a database account with `SELECT` permissions only.
- A database selection made through the UI lasts until the backend restarts. Set `DATABASE_URL` in `backend/.env` (or the Docker `.env`) to configure a persistent default.

### Natural-language analysis

- Highest/lowest and top-N rankings.
- Grouped aggregations, such as revenue by city/product.
- Row/record lookups with configurable limits.
- Known category filters and common relative date periods.
- Wording normalization for common phrases such as `cities`, `total revenue`, and `sales revenue`.
- Schema-aware table/column mapping across the full discovered catalog, including cross-table joins through declared or safely inferred key relationships.
- Domain-language mapping for common solar/energy/performance terms (for example, "solar energy" can map to a real numeric generation column, while "site" can map to a descriptive SiteName column in a related dimension table). Physical identifiers always come from the connected schema.
- SolarPulse-specific analytics for actual-vs-expected generation, energy loss, average performance deviation, Normal/Warning/Critical counts, longest underperformance streak, persistent-underperformance counts, average performance ratio, recent Critical records, and solar-generation trends. These templates are activated only when the required columns are discovered in the connected schema.
- Multi-measure grouped charts: actual and expected generation are plotted as separate grouped-bar or line series rather than collapsing the comparison into a single measure.
- SolarPulse answer templates use the matching aggregate and result rows. Performance deviation is sorted most-negative-first for the "worst deviation" question; average performance ratio is averaged per site and ranked descending.
- Explicit table requests such as "show rows from the performance table" are directed to the named table rather than a guessed first table.
- Unsupported or ambiguous metrics and unrelated tables return a clear error rather than inventing columns or join paths.
- Deterministic local parsing and SQL generation for the supported query shapes. Gemini fallback is optional and disabled by default to avoid quota and latency surprises.

### Visualizations

- Bar chart: category compared with a numeric measure.
- Line chart: date/time or ordered category compared with one or more numeric measures.
- Pie chart: non-negative numeric values split by category.
- Histogram: distribution of a numeric column using raw observations.
- KPI card for single-value results.
- Data table fallback.
- Users can change the chart type in the result panel when the result columns support it.

### Transparency and controls

- SQL validation before execution.
- Single-statement, read-only query flow.
- Row limits and capped recovery retries.
- Grounded answer check and clear handling of empty results.
- Analysis Trace, request metrics, and returned data available in expandable panels.
- Conversation follow-ups within an in-memory session.
- Responsive UI with connection status, loading states, and useful error messages.

## Supported database engines

| Database | Driver | Status |
|---|---|---|
| SQLite | Python built-in driver | Supported; external file connections use read-only mode |
| PostgreSQL | `psycopg` | Supported; configure a read-only database user |
| MySQL | `PyMySQL` | Supported; configure a read-only database user |

The query planner supports **multi-table analytics when a safe relationship path is discoverable**. It follows declared foreign keys and may infer a shared-key relationship only when the key exists in multiple tables and one side is marked as the primary key. It does not guess arbitrary joins. If a database uses unrelated key names and has no declared foreign keys, define those relationships in the database or add a reviewed relationship mapping before asking cross-table questions.

## Requirements

- Windows 10/11, macOS, or Linux.
- Python 3.11 or newer (tested here with Python 3.13).
- Node.js 20 or newer and npm 10 or newer for the React development server.
- Internet access for the initial `pip install` and `npm install`.
- A SQL database reachable from the machine/container running the backend.
- Gemini API key is optional. It is only needed if you enable LLM fallback for questions outside the deterministic supported patterns.
- OpenAI API key is optional and is not required for the default workflow.

## Project layout

```text
natural-language-bi-assistant/
├── backend/
│   ├── app.py                    # FastAPI endpoints, DB connect/reset, sessions
│   ├── assistant.py              # End-to-end BI workflow
│   ├── database.py               # Runtime SQLAlchemy engine manager
│   ├── schema.py                 # Full catalog, keys, relationships, safe table previews
│   ├── db_dialect.py              # SQLite/PostgreSQL/MySQL detection
│   ├── intent.py                 # Local natural-language parsing + optional Gemini fallback
│   ├── query_plan.py              # Intent + discovered schema -> query plan
│   ├── sql_generator.py           # Dialect-aware deterministic SQL generation
│   ├── sql_validator.py           # Read-only SQL/schema validation
│   ├── sql_executor.py            # Capped execution and JSON-safe result values
│   ├── sql_recovery.py            # Limited, revalidated SQL recovery
│   ├── visualization.py           # Chart specification + Plotly helper
│   ├── result_analyzer.py         # Grounded answer templates
│   ├── answer_evaluation.py       # Basic numeric groundedness evaluation
│   ├── observability.py           # Request metrics
│   ├── analysis_trace.py          # User-facing analysis trace
│   ├── api_models.py              # Request/response models
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/main.jsx               # React UI, charts, connection modal
│   ├── src/styles.css             # Responsive deployment-style UI
│   ├── package.json
│   └── nginx.conf                 # Docker reverse proxy
├── context/business_context.json  # Sample-database semantic notes
├── data/bi.db                     # Bundled sample SQLite database
├── db-files/                      # Optional read-only SQLite files for Docker
├── evaluation/benchmark.json
├── tests/
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
└── README.md
```

---

# Run locally on Windows

Running the backend directly on the same Windows machine as your local database is the simplest way to connect SQLite, PostgreSQL, or MySQL databases installed on that machine.

## 1. Extract and open the project

Extract the ZIP, open the `natural-language-bi-assistant` folder in VS Code, and open a PowerShell terminal at the project root.

## 2. Create and activate a Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If script activation is blocked, use Command Prompt:

```bat
.venv\Scripts\activate.bat
```

## 3. Install backend dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

The requirements include the SQL parser plus PostgreSQL and MySQL drivers. A database driver does not install or start the database server itself; the database server/file must already exist and be reachable.

## 4. Configure environment variables

```powershell
Copy-Item backend\.env.example backend\.env
```

Common BI questions run without an LLM key. Keep these defaults initially:

```text
ENABLE_LLM_FALLBACK=false
USE_LLM_ANSWER=false
```

Optional Gemini fallback:

```text
GEMINI_API_KEY=your_private_key
ENABLE_LLM_FALLBACK=true
```

No OpenAI key is required. Never commit `backend/.env` or share screenshots containing secrets.

## 5. Start the backend

```powershell
cd backend
uvicorn app:app --reload
```

Keep this terminal open. The backend listens at `http://127.0.0.1:8000`.

Check:

- Health: `http://127.0.0.1:8000/health`
- API docs: `http://127.0.0.1:8000/docs`
- Active database info: `http://127.0.0.1:8000/api/database`
- Discovered schema: `http://127.0.0.1:8000/api/schema`
- Full database catalog: `http://127.0.0.1:8000/api/database/profile`
- Bounded table preview: `GET /api/database/tables/{table_name}/preview?limit=5`

## 6. Start the React frontend

Open a **second** terminal at the project root:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL Vite prints, usually `http://localhost:5173`.

The browser should show the Data Compass interface and a connected sample database. Use **Manage database** in the left sidebar to connect another SQL database.

---

# Connect your own database

Open **Manage database** in the UI, choose a database type, enter a SQLAlchemy connection URL, and select **Test & connect**. The backend tests `SELECT 1`, discovers accessible tables, and then switches to the new database. It does not create or seed tables in your external database.

## SQLite

Example on Windows:

```text
sqlite:///C:/Users/your-name/Documents/databases/sales.db
```

Example on macOS/Linux:

```text
sqlite:////home/your-name/data/sales.db
```

Use an existing `.db`, `.sqlite`, or `.sqlite3` file. The backend opens a user-selected SQLite database in read-only mode; the file is not modified by assistant queries.

## PostgreSQL

```text
postgresql+psycopg://readonly_user:URL_ENCODED_PASSWORD@localhost:5432/sales_db
```

Create a database account with only the necessary `CONNECT`, schema `USAGE`, and table `SELECT` permissions. For a hosted or remote server, use TLS and restrict network access to the backend host.

## MySQL

```text
mysql+pymysql://readonly_user:URL_ENCODED_PASSWORD@127.0.0.1:3306/sales_db
```

Use a MySQL account with `SELECT` privileges only. URL-encode special characters in usernames/passwords. For example, `@` becomes `%40` and `/` becomes `%2F`.

## What happens after connecting?

- The backend introspects all accessible tables/views in the active/default schema and records column types, primary keys, foreign keys, and safe relationship paths.
- The UI shows the database name/type and table count; Database Explorer lists every table, columns, key flags, and relationships.
- Each table can be previewed on demand (up to five rows) so a user can inspect its actual shape without downloading the entire table.
- The query planner searches the full connected schema instead of the sample `sales` schema, and joins related fact/dimension tables when a relationship path exists.
- A bounded sample of text-category values is read from each eligible table to support filters such as a specific site or product; it is capped and is not a full database import.
- Common supported questions use deterministic rules and SQL generation.
- Queries are restricted to read-only SELECT statements and capped result sizes.
- The connection URL stays in backend memory and is not returned to the browser or written into a project file.
- Restarting the backend restores the default database from `DATABASE_URL` (or the bundled demo database if not configured).

To make a database the default after restart, set its URL in `backend/.env` as `DATABASE_URL=...`. Protect that file and do not commit it.

### Important local-database deployment boundary

A browser hosted in the cloud cannot directly open a database file on a user's personal computer. The backend must run on the same machine/network as the database, or the database must be reachable through a properly secured private network/VPN/tunnel. Do not expose a local database port to the public internet just to make it connect.

---

# Charts and question examples

The assistant chooses a chart from the query/result shape. You can also select another compatible chart in the result panel.

| Question | Expected chart/result |
|---|---|
| `Which city generated the highest revenue?` | KPI/ranking result |
| `What are the top 4 cities with highest revenue?` | Bar chart; fewer than 4 if fewer categories exist |
| `What is the total revenue generated by each city?` | Bar chart |
| `Generate a bar chart for revenue by city` | Bar chart |
| `Generate a line chart for revenue over time` | Line chart using a date/time column |
| `Generate a pie chart for revenue by city` | Pie chart when values are non-negative |
| `Show a histogram of revenue` | Histogram built from raw numeric observations |
| `Show me 10 rows of the dataset` | Data table |
| `Which Solar Site generates the most solar energy?` | Site-level KPI/ranking using a join to the site dimension |
| `What are the top 4 solar sites with highest performance?` | Ranked site table/bar using the performance metric and site relationship |
| `Generate a bar chart for solar generation by site` | Bar chart across related generation/site tables |
| `Generate a line chart of solar energy over time` | Line chart grouped by a discovered timestamp/date column |
| `Give me all rows from performance_results` | Bounded preview of the explicitly named table |
| `Read all the tables in the database` | Database catalog showing every discovered table/view |

Chart requirements:

- Bar, line, and pie need a category/time column plus a numeric measure.
- Line charts need an appropriate date/time field or another ordered category.
- Histograms need one numeric column.
- Pie charts require non-negative values with a positive total. If not, the UI offers a table/bar alternative rather than showing a misleading pie chart.
- A request for the top four categories returns only the categories that actually exist in the database.

For user databases with unusual field names, use Database Explorer to inspect the discovered schema and add a business definition/alias in the context layer if the physical name does not express the measure's meaning. Joins require a declared foreign key or a conservative shared-primary-key match; the assistant deliberately refuses to invent a relationship.

---

# Deployment with Docker Compose

Docker Compose runs the FastAPI backend and the built React/Nginx frontend. It is intended for self-hosted deployment on a machine/network that can reach the selected database.

## 1. Configure Compose environment

Copy:

```powershell
Copy-Item .env.docker.example .env
```

Edit `.env` if you want to configure an LLM fallback or a default database URL. Keep secrets out of Git.

## 2. Build and start

From the project root:

```powershell
docker compose up --build -d
```

Open:

```text
http://localhost:8080
```

Inspect logs:

```powershell
docker compose logs -f backend
docker compose logs -f frontend
```

Stop:

```powershell
docker compose down
```

## Connect a database from Docker

- **PostgreSQL/MySQL running on the host:** use `host.docker.internal` as the host in the UI connection URL, and ensure the server listens on an interface reachable from Docker with firewall rules restricted to the local Docker host.
- **SQLite file:** place the database file in the project `db-files/` folder. Compose mounts that folder read-only at `/db-files`. Connect using a URL such as `sqlite:////db-files/your-database.db`.
- **Remote database:** use its private DNS/IP and a least-privilege user. Use VPN/private networking or TLS; do not publish a database port publicly.

The Docker setup was source-checked but could not be executed in the build environment used to prepare this ZIP because Docker was unavailable. Run `docker compose up --build` on your machine to validate your environment-specific image build and network access.

---

# Tests and evaluation

From the project root with the Python virtual environment activated:

```powershell
python -m pytest
```

The package includes unit and integration tests for database connection switching, read-only SQLite connections, multi-table schema discovery, relationship resolution, cross-table Solar-style questions, bounded table previews, SQL identifier quoting, SQL generation/validation/recovery, all four chart specifications/figures, API behaviour, and the assistant pipeline. The current prepared package test count is 164.

Run the small analytical benchmark:

```powershell
cd backend
python run_evaluation.py
```

Tests do not require a live Gemini or OpenAI key. The standard deterministic questions do not use Gemini when `ENABLE_LLM_FALLBACK=false`.

---

# Security and production checklist

This project is prepared for controlled self-hosted use, not a public multi-tenant service. Before exposing it to a wider audience:

1. Put the frontend/backend behind HTTPS and an authentication gateway.
2. Add user authentication and authorisation before allowing database connection changes.
3. Implement per-user database connection pools and isolate sessions/connections; the current app uses one active process-wide connection.
4. Use read-only database accounts for PostgreSQL/MySQL. SQLite user connections are opened in read-only mode.
5. Keep database credentials and LLM API keys in a secret manager or protected environment file, never in frontend code.
6. Restrict database network access to the backend host/container.
7. Review query timeout, row caps, resource use, audit logging, and retention for the target database.
8. Configure `CORS_ORIGINS` with only the exact frontend origins when frontend and backend are hosted separately.
9. Do not run this service as a public anonymous endpoint; the API currently has no built-in user authentication or per-user tenant isolation.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Default SQLAlchemy database URL | Bundled SQLite sample |
| `GEMINI_API_KEY` | Optional Gemini fallback key | Empty |
| `GEMINI_MODEL` | Gemini fallback model | `gemini-3.6-flash` |
| `ENABLE_LLM_FALLBACK` | Allow Gemini for unsupported wording/query shapes | `false` |
| `USE_LLM_ANSWER` | Optional LLM answer rewriting | `false` |
| `MAX_RESULT_ROWS` | Maximum rows fetched for a result | `200` |
| `MAX_RECOVERY_RETRIES` | Maximum SQL recovery retries | `1` |
| `CORS_ORIGINS` | Comma-separated exact browser origins | Local Vite origins |

OpenAI configuration remains optional. No OpenAI API key is needed for the default project workflow.

## Troubleshooting

- **`Failed to fetch`:** make sure FastAPI is running at `http://127.0.0.1:8000`; check `frontend/.env` if you changed the API URL.
- **CORS error:** add the exact frontend origin to `CORS_ORIGINS` in `backend/.env`, then restart FastAPI.
- **SQLite file not found:** check the absolute path and ensure the backend process can read the file.
- **PostgreSQL/MySQL driver missing:** reinstall `backend/requirements.txt` in the active virtual environment.
- **Connection refused/timeouts:** verify that the database server is running, listening on the expected interface/port, and reachable from the backend host/container.
- **No accessible tables:** verify schema/table permissions and that the selected database/schema contains tables.
- **Question not matched to a metric:** open Database Explorer, check which numeric measure column exists, and use that field name or add a business alias.
- **Cross-table question cannot find a related dimension:** check that the database has a foreign-key constraint or matching primary-key/shared-key columns. The planner will not guess arbitrary joins.
- **Chart not displayed:** confirm the result includes a numeric measure and a category/date column. Bar/pie need category + measure; line needs at least two observations and an axis; histogram needs a numeric column.
- **Table has no preview values:** confirm the selected database account has `SELECT` permission on that table/view.
- **LLM quota/rate limit:** common supported query patterns should still run locally. Keep `ENABLE_LLM_FALLBACK=false` unless you explicitly need LLM fallback.

## Scope and limitations

- Multi-table joins are supported only for discovered FK relationships or conservative shared-key links; arbitrary joins are not inferred.
- Runtime UI connections last until backend restart unless configured as `DATABASE_URL`.
- Conversation history is in memory and is cleared when the process restarts or the database is switched.
- Common domain terms are mapped heuristically from the question and actual column/table names. Custom metric definitions, units, exclusions, and business rules still need to be added to the context layer; schema introspection cannot infer every company's business meaning.
- Hosted deployments cannot access a personal computer's database file without a secure network route or a locally running backend/agent.
- The optional LLM fallback may return provider quota/capacity errors; it is disabled by default.
