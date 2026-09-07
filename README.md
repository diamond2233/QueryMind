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

* `querymind_openai.ipynb` – The project: SQL generation, execution, answer generation, and RAGAS evaluation, in one notebook
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
   pip install langchain langchain-openai "langchain-community==0.3.31" openai pymysql sqlalchemy "ragas==0.3.9" ipykernel
   ```

3. Have a MySQL server running locally with a `text_to_sql` database (see `Data_CSV/` for the source data).

4. Set your OpenAI API key as an environment variable (or let the notebook prompt for it via `getpass`):

   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

5. Open and run `querymind_openai.ipynb` top to bottom in Jupyter or VS Code.

## Note

Keep API keys and database credentials out of version control — the notebook reads them from
environment variables or an interactive `getpass` prompt, never hardcoded.

## License

Add a license if you want to make the project easier to reuse.
