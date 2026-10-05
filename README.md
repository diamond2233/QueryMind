# QueryMind

QueryMind is a natural-language-to-SQL project: it takes a plain-English question, uses an
OpenAI chat model to translate it into a SQL query, checks the query with a safety guard,
runs it against a MySQL database, and turns the result back into a plain-language answer.
It comes with a small benchmark that measures how often the generated SQL returns the right
rows.

## Features

* Natural language question &rarr; SQL query generation (`gpt-4.1-mini`, temperature 0)
* Live execution against a MySQL database, behind a safety guard
* Repair loop: if MySQL rejects the SQL, the model gets the exact error and fixes it (up to 2 times)
* Natural-language answer generation from the SQL result
* Execution-accuracy benchmark: 30 questions with hand-checked gold SQL
* Tests with a fake LLM and a fake database, so they need no OpenAI key or MySQL
* Built with LangChain Expression Language (LCEL) — no agents, no RAG, no vector store

## How it works

1. The user asks a question in natural language.
2. The live database schema is retrieved and given to the model as context.
3. The model (`gpt-4.1-mini`) generates a SQL query for the question.
4. The query passes a safety guard and runs against the MySQL database. If MySQL rejects it
   (e.g. a syntax error), the model is shown the exact error and asked to fix it, up to 2 times.
5. The model turns the raw SQL result into a concise natural-language answer.

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/diamond2233/QueryMind.git
   cd QueryMind
   ```

2. Install the dependencies (pinned versions, tested with Python 3.13):

   ```bash
   pip install -r requirements.txt
   ```

3. Create a MySQL database called `text_to_sql` and load the six CSV files from `Data_CSV/`
   into it, one table per file. The table name is the file name in lowercase without `.csv`
   (`2017_budgets`, `customers`, `products`, `regions`, `sales_order`, `state_regions`), and
   the column names are exactly the CSV headers. The repo has no loader script yet, so this
   step is manual (for example with your MySQL client's CSV import).

4. Copy `.env.example` to `.env` and fill in your OpenAI key and MySQL settings
   (`OPENAI_API_KEY`, `OPENAI_MODEL`, `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`,
   `MYSQL_DATABASE`). Real environment variables work too.

5. Create a read-only MySQL user (as an admin user) and put it in `.env` as `MYSQL_USER` and
   `MYSQL_PASSWORD`:

   ```sql
   CREATE USER 'querymind_ro'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
   GRANT SELECT ON text_to_sql.* TO 'querymind_ro'@'localhost';
   ```

## Usage

Ask a question from the command line:

```bash
python querymind.py "What was the 2017 budget for Product 12?"
```

It prints the question, the SQL that ran, the result rows and the answer. If the safety guard
refuses the generated SQL, it says so and runs nothing.

Run the tests (no OpenAI key or MySQL needed):

```bash
python -m pytest
```

## Safety

The SQL is written by an LLM, so it is never run unchecked. `check_sql_is_safe` (called inside
`run_query`) only allows a single `SELECT`/`WITH` statement, rejects write/DDL keywords
(`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REPLACE`), SQL
comments and extra `;`, and adds `LIMIT 100` when there is no `LIMIT`. Unsafe SQL raises
`UnsafeSQLError`.

That check is only a blocklist and can be wrong in both directions. **The real protection is a
read-only MySQL user** (see Setup, step 5): even if a bad query got through, MySQL itself would
refuse to change anything.

Keep API keys and database credentials out of version control — `querymind.py` reads them from
environment variables or a `.env` file (which is gitignored), never hardcoded.

## Reproduce the numbers

1. Check that every gold query still runs and returns rows (no OpenAI calls):

   ```bash
   python scripts/verify_gold.py
   ```

2. Run the evaluation without repairs (behaves like the baseline) and with up to 2 repairs:

   ```bash
   python scripts/run_eval.py --runs 3 --max-repairs 0 --output results/repair0_check.json
   python scripts/run_eval.py --runs 3 --max-repairs 2 --output results/repair_loop.json
   ```

   Each command makes about 90 OpenAI calls and writes a summary plus a `*_details.json` file.
   These commands overwrite the committed results; use another `--output` file to keep them.
   Without `--output`, results go to `results/latest.json`. The run also lists which
   questions changed compared with `results/baseline_details.json`.

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
* Only the rows are scored. The natural-language answer written from them is not checked.
* There is no loader script yet: the database has to be loaded from `Data_CSV/` by hand.

## Project structure

```
querymind.py              the app: plain functions (load_config, get_db, generate_sql,
                          check_sql_is_safe, run_query, answer_with_repair,
                          answer_question) plus the command-line entry
evalcheck.py              result comparison, labelling and summaries for the evaluation
eval/questions.json       30 questions with hand-checked gold SQL (10 dev, 20 test)
scripts/verify_gold.py    runs every gold query and prints it for review
scripts/run_eval.py       measures execution accuracy (--runs, --split, --max-repairs, --output)
results/                  baseline.json, repair0_check.json, repair_loop.json
                          (+ a *_details.json file for each)
tests/                    test_guard.py, test_pipeline.py, test_compare.py,
                          test_run_eval.py, test_repair.py
docs/                     Q1_EXPLAINED.md … Q4_EXPLAINED.md, plain-language explanations
Data_CSV/                 the six source CSV files for the text_to_sql database
requirements.txt          pinned Python dependencies
pytest.ini                test settings
.env.example              template for your settings (copy to .env, which is gitignored)
```
