# Chat With Database

Ask questions in natural language about a Railway PostgreSQL database (Chinook). The question is converted to SQL, executed, and the result is answered in plain language.

## Structure (MVC)

```
app/
  main.py          FastAPI app
  config.py        environment settings
  models/          database access (engine, schema introspection, SQL execution)
  views/           request/response schemas
  controllers/     chat flow: question -> SQL -> result -> answer
  routes/          FastAPI endpoints
  services/        LLM calls (Azure OpenAI)
scripts/deploy.py  loads data/*.csv into the database
```

## Run

```
cp .env.example .env   # fill in values
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`POST /chat` with `{"question": "Which artist has the most albums?"}`
