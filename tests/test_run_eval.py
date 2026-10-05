"""Tests for the labelling logic in evalcheck, with a fake LLM and a fake database.
No real OpenAI or MySQL calls are made."""

import pymysql
import sqlalchemy.exc
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import evalcheck
import querymind


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeDB:
    """Pretends to be the LangChain SQLDatabase. Returns the given rows, or raises
    the given error, and remembers which SQL was run."""

    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.executed = []

    def get_table_info(self):
        return "CREATE TABLE products (`Index` INTEGER, `Product Name` TEXT)"

    def run(self, sql, fetch="all"):
        self.executed.append(sql)
        if self.error:
            raise self.error
        return FakeCursor(self.rows)


def use_fakes(monkeypatch, llm_sql, rows=None, error=None):
    """Replace get_db and get_llm in querymind with fakes. Returns the fake DB."""
    fake_db = FakeDB(rows, error)
    fake_llm = FakeListChatModel(responses=[llm_sql])
    monkeypatch.setattr(querymind, "get_db", lambda: fake_db)
    monkeypatch.setattr(querymind, "get_llm", lambda: fake_llm)
    return fake_db


GOLD = [("Product 26",)]


def test_correct(monkeypatch):
    use_fakes(monkeypatch, "SELECT `Product Name` FROM products", rows=[("Product 26",)])
    result = evalcheck.evaluate_question("Best product?", GOLD)
    assert result["label"] == "correct"
    assert result["row_count"] == 1
    assert result["generated_sql"] == "SELECT `Product Name` FROM products"


def test_correct_extra_columns(monkeypatch):
    use_fakes(monkeypatch, "SELECT `Product Name`, SUM(x) FROM t", rows=[("Product 26", 50364)])
    assert evalcheck.evaluate_question("Best product?", GOLD)["label"] == "correct_extra_columns"


def test_wrong_result(monkeypatch):
    use_fakes(monkeypatch, "SELECT `Product Name` FROM products", rows=[("Product 25",)])
    assert evalcheck.evaluate_question("Best product?", GOLD)["label"] == "wrong_result"


def test_sql_error_keeps_mysql_code_and_message(monkeypatch):
    mysql_error = pymysql.err.OperationalError(1054, "Unknown column 'nope' in 'field list'")
    error = sqlalchemy.exc.OperationalError("SELECT nope", {}, mysql_error)
    use_fakes(monkeypatch, "SELECT nope FROM products", error=error)

    result = evalcheck.evaluate_question("Best product?", GOLD)

    assert result["label"] == "sql_error"
    assert result["error_code"] == 1054
    assert result["error"] == "Unknown column 'nope' in 'field list'"


def test_unsafe_sql_is_labelled_and_never_executed(monkeypatch):
    fake_db = use_fakes(monkeypatch, "SELECT 1; DROP TABLE products", rows=[("x",)])

    result = evalcheck.evaluate_question("Best product?", GOLD)

    assert result["label"] == "unsafe_sql"
    assert "one SQL statement" in result["error"]
    assert fake_db.executed == []


def test_generation_error_does_not_crash(monkeypatch):
    def broken_generate_sql(question):
        raise RuntimeError("OpenAI is down")

    fake_db = use_fakes(monkeypatch, "unused", rows=[("x",)])
    monkeypatch.setattr(querymind, "generate_sql", broken_generate_sql)

    result = evalcheck.evaluate_question("Best product?", GOLD)

    assert result["label"] == "generation_error"
    assert result["error"] == "RuntimeError: OpenAI is down"
    assert fake_db.executed == []


def record(run, question_id, difficulty, split, label):
    return {"run": run, "id": question_id, "difficulty": difficulty, "split": split,
            "label": label, "seconds": 1.0}


def test_summarize_counts_both_correct_labels_and_finds_changes():
    details = [
        record(1, "q1", "easy", "dev", "correct"),
        record(1, "q2", "hard", "test", "correct_extra_columns"),
        record(2, "q1", "easy", "dev", "correct"),
        record(2, "q2", "hard", "test", "wrong_result"),
    ]

    summary = evalcheck.summarize(details, "fake-model", "all", runs=2)

    assert summary["correct_per_run"] == ["2 of 2", "1 of 2"]
    assert summary["median_correct"] == "1.5 of 2"
    assert summary["exact_per_run"] == [1, 1]
    assert summary["extra_columns_per_run"] == [1, 0]
    assert summary["by_difficulty"]["hard"]["correct_per_run"] == ["1 of 1", "0 of 1"]
    assert summary["by_split"]["dev"]["median_correct"] == "1 of 1"
    assert summary["label_counts"]["wrong_result"] == 1
    assert summary["changed_between_runs"] == [
        {"id": "q2", "labels": ["correct_extra_columns", "wrong_result"]}
    ]
