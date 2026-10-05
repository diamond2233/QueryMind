# QueryMind

QueryMind is a natural-language-to-SQL project: it takes a plain-English question, uses an
OpenAI chat model to translate it into a SQL query, runs that query against a MySQL database,
and turns the result back into a plain-language answer.

## Features

* Natural language question &rarr; SQL query generation
* Live execution against a MySQL database, behind a safety guard
* Repair loop: if MySQL rejects the SQL, the model gets the exact error and fixes it (up to 2 times)
* Natural-language answer generation from the SQL result
* Automated quality evaluation with [RAGAS](https://docs.ragas.io/) (context precision, helpfulness)
* Built with LangChain Expression Language (LCEL) — no agents, no RAG, no vector store

## Project Structure

* `querymind.py` – The project logic as plain functions (`load_config`, `get_db`, `generate_sql`, `check_sql_is_safe`, `run_query`, `answer_with_repair`, `answer_question`) plus a command-line entry
* `evalcheck.py` – Result comparison and labelling for the evaluation
* `eval/questions.json` – 30 test questions with hand-checked gold SQL
* `scripts/verify_gold.py`, `scripts/run_eval.py` – Check the gold SQL; measure execution accuracy
* `results/` – Evaluation results (baseline and repair loop)
* `tests/` – Tests with a fake LLM and a fake database (no OpenAI or MySQL needed)
* `docs/Q1_EXPLAINED.md` … `docs/Q4_EXPLAINED.md` – Plain-language explanations of each step
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
4. The query passes a safety guard and runs against the MySQL database. If MySQL rejects it
   (e.g. a syntax error), the model is shown the exact error and asked to fix it, up to 2 times.
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

## Results

Execution accuracy on 30 questions (the model's SQL must return the same rows as the gold
SQL), `gpt-4.1-mini`, 3 runs each. All three runs gave the same score. Numbers come from
`results/baseline.json` and `results/repair_loop.json` (the baseline's LLM-call count from
`results/repair0_check.json`, a re-run with repairs off that matched the baseline exactly);
see `docs/Q3_EXPLAINED.md` and `docs/Q4_EXPLAINED.md`.

| | Baseline (no repairs) | Repair loop (up to 2 repairs) |
|---|---|---|
| **Overall** | **26 of 30** | **29 of 30** |
| easy / medium | 8 of 8 / 8 of 8 | 8 of 8 / 8 of 8 |
| join | 6 of 8 | 8 of 8 |
| hard | 4 of 6 | 5 of 6 |
| dev / test | 8 of 10 / 18 of 20 | 10 of 10 / 19 of 20 |
| SQL errors (90 attempts) | 9 | 0 |
| Avg. LLM calls for SQL per question | 1 | 1.1 |

The repair loop fixed q17, q22 and q25 (a column name with a space, written without
backticks). No question got worse. q30 is still wrong: its SQL runs but gives the wrong
rows, which a repair loop can't detect.

## Limitations

* Only 30 questions, on one small database with 6 tables. Small changes move the score a lot
  (1 question = 3.3 percentage points).
* The questions and gold SQL were written with AI help (and checked by hand), not by real
  business users.
* The repair prompt was designed *after* seeing the baseline failures, and its "use
  backticks" instruction targets exactly that mistake. The improvement may be smaller on new
  questions.
* Row order is ignored when comparing results, so a "top 3" list in the wrong order still
  counts as correct.
* Results with extra columns (the right answer plus e.g. a count) are counted as correct.

## Note

Keep API keys and database credentials out of version control — `querymind.py` reads them from
environment variables or a `.env` file (which is gitignored), never hardcoded.

## License

Add a license if you want to make the project easier to reuse.
