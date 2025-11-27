# Commitment Tracker (FastAPI + Jinja2 + PostgreSQL)

## How to Run
1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Set environment variables:
   ```
   export DATABASE_URL="postgresql://postgres:password@localhost:5432/mydb"
   export SECRET_KEY="mysecret"
   ```
3. Start the server:
   ```
   uvicorn main:app --reload
   ```
4. Open in browser: http://127.0.0.1:8000/
