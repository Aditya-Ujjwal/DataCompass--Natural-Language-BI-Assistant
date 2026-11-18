# Backend

FastAPI app for the Natural Language BI Assistant. Read the root `README.md` for complete setup instructions.

Quick start from this folder:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and add GEMINI_API_KEY if you want LLM fallback for unfamiliar questions.
uvicorn app:app --reload
```
