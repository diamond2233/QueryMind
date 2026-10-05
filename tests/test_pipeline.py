"""Tests for answer_question with a fake LLM and a fake database.
No real OpenAI or MySQL calls are made."""

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import querymind


class FakeDB:
    """Pretends to be the LangChain SQLDatabase and remembers which SQL was run."""

    def __init__(self):
        self.executed = []

    def get_table_info(self):
        return "CREATE TABLE products (`Index` INTEGER, `Product Name` TEXT)"

    def run(self, sql):
        self.executed.append(sql)
        return "[('Product 1',), ('Product 2',)]"


def use_fakes(monkeypatch, llm_replies):
    """Replace get_db and get_llm in querymind with fakes. Returns the fake DB."""
    fake_db = FakeDB()
    # The fake LLM returns these replies in order: first the SQL, then the answer.
    fake_llm = FakeListChatModel(responses=llm_replies)
    monkeypatch.setattr(querymind, "get_db", lambda: fake_db)
    monkeypatch.setattr(querymind, "get_llm", lambda: fake_llm)
    return fake_db


def test_answer_question_returns_sql_rows_and_answer(monkeypatch):
    fake_db = use_fakes(monkeypatch, [
        "```sql\nSELECT `Product Name` FROM products;\n```",
        "The products are Product 1 and Product 2.",
    ])

    result = querymind.answer_question("What are the product names?")

    assert result["question"] == "What are the product names?"
    assert result["sql"] == "SELECT `Product Name` FROM products LIMIT 100"
    assert result["rows"] == "[('Product 1',), ('Product 2',)]"
    assert result["answer"] == "The products are Product 1 and Product 2."
    # The SQL that ran is the checked one, with LIMIT 100 added.
    assert fake_db.executed == ["SELECT `Product Name` FROM products LIMIT 100"]


def test_unsafe_sql_from_llm_is_rejected_and_not_executed(monkeypatch):
    fake_db = use_fakes(monkeypatch, ["SELECT 1; DROP TABLE products", "should never be used"])

    with pytest.raises(querymind.UnsafeSQLError):
        querymind.answer_question("Please delete everything")

    assert fake_db.executed == []


def test_run_query_checks_before_executing(monkeypatch):
    # Even if someone calls run_query directly, unsafe SQL never reaches the database.
    fake_db = use_fakes(monkeypatch, [])

    with pytest.raises(querymind.UnsafeSQLError):
        querymind.run_query("DROP TABLE products")

    assert fake_db.executed == []
