# Frontend — Natural Language BI Assistant

React + Vite interface for the FastAPI BI assistant.

## Install and run

```bash
npm install
npm run dev
```

Start the backend in a separate terminal first (see the root setup guide). The default API base is `http://127.0.0.1:8000`; override it with `VITE_API_URL` if needed.

## Database Explorer

After connecting a database, the sidebar refreshes the full database catalog. Expand any table/view to inspect column names, types, primary/foreign-key markers, and click **Preview 5 rows** for a bounded sample. The explorer also lists discovered relationships used by the multi-table query planner.

## Visualizations

The result area renders bar charts, line charts, pie/donut charts, histograms, KPI cards, or a returned-data table using the actual columns/rows returned by the database. Chart type choices are limited to those compatible with the result.
