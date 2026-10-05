# QueryMind

QueryMind is a natural-language-to-SQL project: it takes a plain-English question, uses an
OpenAI chat model to translate it into a SQL query, runs that query against a MySQL database,
and turns the result back into a plain-language answer.

## Features

* Natural language question &rarr; SQL query generation
* Live execution against a MySQL database
* Natural-language answer generation from the SQL result
* Automated quality evaluation with [RAGAS](https://docs.ragas.io/) (context precision, helpfulness)
* Built with LangChain Expression Language (LCEL) — no agents, no RAG, no vector store

## Project Structure

* `querymind.py` – The project logic as plain functions (`load_config`, `get_db`, `generate_sql`, `run_query`, `answer_question`) plus a command-line entry
* `querymind_openai.ipynb` – Short demo notebook that imports `querymind.py`, plus the RAGAS evaluation
* `requirements.txt` – Python dependencies
* `.env.example` – Template for your settings (copy to `.env`, which is gitignored)
* `Data_CSV/` – Source CSV files loaded into the MySQL `text_to_sql` database (budgets, customers, products, regions, sales orders, state/region mapping)

## Tech Stack

* Python
* Jupyter Notebook
* OpenAI API (`gpt-4.1-mini`)
* LangChain / LangChain Expression Language (LCEL)
* MySQL (via `SQLAlchemy` + `PyMySQL`)
* RAGAS (evaluation)

## How It Works

1. The user asks a question in natural language.
2. The live database schema is retrieved and given to the model as context.
3. The model (`gpt-4.1-mini`) generates a SQL query for the question.
4. The query runs against the MySQL database.
5. The model turns the raw SQL result into a concise natural-language answer.
6. A small held-out question set is scored with RAGAS to sanity-check SQL-generation quality.

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/diamond2233/QueryMind.git
   cd QueryMind
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Have a MySQL server running locally with a `text_to_sql` database (see `Data_CSV/` for the source data).

4. Copy `.env.example` to `.env` and fill in your OpenAI key and MySQL settings
   (`OPENAI_API_KEY`, `OPENAI_MODEL`, `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`).
   Real environment variables work too.

5. Ask a question from the command line:

   ```bash
   python querymind.py "What was the 2017 budget for Product 12?"
   ```

   Or open `querymind_openai.ipynb` for the demo and the RAGAS evaluation.

## Safety

The SQL is written by an LLM, so it is never run unchecked. `check_sql_is_safe` (called inside
`run_query`) only allows a single `SELECT`/`WITH` statement, rejects write/DDL keywords
(`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REPLACE`), SQL
comments and extra `;`, and adds `LIMIT 100` when there is no `LIMIT`. Unsafe SQL raises
`UnsafeSQLError`.

That check is only a blocklist and can be wrong in both directions. **The real protection is a
read-only MySQL user**: even if a bad query got through, MySQL itself would refuse to change
anything. Create one (as an admin user) and put it in your `.env`:

```sql
CREATE USER 'querymind_ro'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
GRANT SELECT ON text_to_sql.* TO 'querymind_ro'@'localhost';
```

Then set `MYSQL_USER=querymind_ro` and `MYSQL_PASSWORD=...` in `.env`.

## Note

Keep API keys and database credentials out of version control — `querymind.py` reads them from
environment variables or a `.env` file (which is gitignored), never hardcoded.

## License

Add a license if you want to make the project easier to reuse.
