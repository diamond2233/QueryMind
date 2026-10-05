"""QueryMind: ask a question in plain English, get SQL, run it on MySQL, get an answer.

Same logic as querymind_openai.ipynb, written as plain functions.

Usage:
    python querymind.py "What was the 2017 budget for Product 12?"
"""

import os
import re
import sys
import warnings
from urllib.parse import quote_plus

from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=DeprecationWarning)

from langchain_community.utilities import SQLDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


SQL_GEN_TEMPLATE = """You are a MySQL expert. Given an input question, write a syntactically \
correct MySQL query to answer it.
Only use the tables and columns shown in the schema below. Return ONLY the SQL query — no \
explanation, no Markdown code fences, no trailing semicolon.

Schema:
{schema}

Question: {question}
SQL Query:"""

ANSWER_TEMPLATE = """Given the question, the SQL query used, and the SQL result, write a \
concise natural-language answer.

Question: {question}
SQL Query: {query}
SQL Result: {result}

Answer:"""

# Created once on first use, then reused (so we don't reconnect for every question).
_db = None
_llm = None


def load_config():
    """Read settings from environment variables (and from a .env file, if there is one)."""
    load_dotenv()

    required = ["OPENAI_API_KEY", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"]
    missing = [name for name in required if os.environ.get(name) is None]
    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing)
            + ". Copy .env.example to .env and fill it in."
        )

    return {
        "openai_api_key": os.environ["OPENAI_API_KEY"],
        "openai_model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "mysql_host": os.environ.get("MYSQL_HOST", "localhost"),
        "mysql_port": os.environ.get("MYSQL_PORT", "3306"),
        "mysql_user": os.environ["MYSQL_USER"],
        "mysql_password": os.environ["MYSQL_PASSWORD"],
        "mysql_database": os.environ["MYSQL_DATABASE"],
    }


def get_db():
    """Connect to MySQL (only the first time) and return the LangChain SQLDatabase."""
    global _db
    if _db is None:
        config = load_config()
        # quote_plus so special characters like '@' in the password don't break the URI
        mysql_uri = (
            f"mysql+pymysql://{config['mysql_user']}:{quote_plus(config['mysql_password'])}"
            f"@{config['mysql_host']}:{config['mysql_port']}/{config['mysql_database']}"
        )
        _db = SQLDatabase.from_uri(mysql_uri, sample_rows_in_table_info=2)
    return _db


def get_llm():
    """Create the OpenAI chat model (only the first time) and return it."""
    global _llm
    if _llm is None:
        config = load_config()
        _llm = ChatOpenAI(
            model=config["openai_model"],
            api_key=config["openai_api_key"],
            temperature=0,
        )
    return _llm


def clean_sql(text):
    """Strip Markdown code fences and a trailing semicolon the model might add."""
    text = text.strip()
    match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1).strip()
    return text.rstrip(";").strip()


def generate_sql(question):
    """Ask the LLM to write a SQL query for the question, using the live schema."""
    schema = get_db().get_table_info()
    chain = ChatPromptTemplate.from_template(SQL_GEN_TEMPLATE) | get_llm() | StrOutputParser()
    text = chain.invoke({"schema": schema, "question": question})
    return clean_sql(text)


def run_query(sql):
    """Run the SQL on MySQL and return the result rows (as a string)."""
    return get_db().run(sql)


def answer_question(question):
    """Full pipeline: question -> SQL -> rows -> natural-language answer."""
    sql = generate_sql(question)
    rows = run_query(sql)

    chain = ChatPromptTemplate.from_template(ANSWER_TEMPLATE) | get_llm() | StrOutputParser()
    answer = chain.invoke({"question": question, "query": sql, "result": rows})

    return {"question": question, "sql": sql, "rows": rows, "answer": answer}


def main():
    if len(sys.argv) != 2:
        print('Usage: python querymind.py "your question"')
        sys.exit(1)

    result = answer_question(sys.argv[1])
    print("Question:", result["question"])
    print("SQL:     ", result["sql"])
    print("Rows:    ", result["rows"])
    print("Answer:  ", result["answer"])


if __name__ == "__main__":
    main()
