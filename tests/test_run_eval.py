"""Tests for the labelling logic in evalcheck, with a fake LLM and a fake database.
No real OpenAI or MySQL calls are made."""

import pymysql
import sqlalchemy.exc
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import evalcheck
import querymind


class FakeCursor:
    """Pretends to be the cursor that db.run(sql, fetch="cursor") returns."""

    def __init__(self, rows):
        self.rows = rows

    def keys(self):
        return [f"column{i}" for i in range(len(self.rows[0]))] if self.rows else []

    def fetchall(self):
        return self.rows


class FakeDB:
    """Pretends to be the LangChain SQLDatabase. Returns the given rows, or raises
    the given error (only the first `fail_times` times, if set), and remembers which
    SQL was run."""

    def __init__(self, rows=None, error=None, fail_times=None):
        self.rows = rows or []
        self.error = error
        self.fail_times = fail_times
        self.executed = []

    def get_table_info(self):
        return "CREATE TABLE products (`Index` INTEGER, `Product Name` TEXT)"

    def run(self, sql, fetch="all"):
        self.executed.append(sql)
        still_failing = self.fail_times is None or len(self.executed) <= self.fail_times
        if self.error and still_failing:
            raise self.error
        return FakeCursor(self.rows)


def use_fakes(monkeypatch, llm_sql, rows=None, error=None, fail_times=None):
    """Replace get_db and get_llm in querymind with fakes. Returns the fake DB.
    llm_sql is one reply, or a list of replies (first the SQL, then each repair)."""
    fake_db = FakeDB(rows, error, fail_times)
    replies = llm_sql if isinstance(llm_sql, list) else [llm_sql]
    fake_llm = FakeListChatModel(responses=replies)
    monkeypatch.setattr(querymind, "get_db", lambda: fake_db)
    monkeypatch.setattr(querymind, "get_llm", lambda: fake_llm)
    return fake_db


GOLD = [("Product 26",)]


def test_correct(monkeypatch):
    use_fakes(monkeypatch, "SELECT `Product Name` FROM products", rows=[("Product 26",)])
    result = evalcheck.evaluate_question("Best product?", GOLD)
    assert result["label"] == "correct"
    assert result["row_count"] == 1
    assert result["final_sql"] == "SELECT `Product Name` FROM products LIMIT 100"
    assert result["attempts"] == 1
    assert result["error_history"] == []


def test_correct_extra_columns(monkeypatch):
    use_fakes(monkeypatch, "SELECT `Product Name`, SUM(x) FROM t", rows=[("Product 26", 50364)])
    assert evalcheck.evaluate_question("Best product?", GOLD)["label"] == "correct_extra_columns"


def test_wrong_result(monkeypatch):
    use_fakes(monkeypatch, "SELECT `Product Name` FROM products", rows=[("Product 25",)])
    assert evalcheck.evaluate_question("Best product?", GOLD)["label"] == "wrong_result"


def unknown_column_error():
    mysql_error = pymysql.err.OperationalError(1054, "Unknown column 'nope' in 'field list'")
    return sqlalchemy.exc.OperationalError("SELECT nope", {}, mysql_error)


def test_sql_error_keeps_mysql_code_and_message(monkeypatch):
    use_fakes(monkeypatch, "SELECT nope FROM products", error=unknown_column_error())

    result = evalcheck.evaluate_question("Best product?", GOLD, max_repairs=0)

    assert result["label"] == "sql_error"
    assert result["error_code"] == 1054
    assert result["error"] == "Unknown column 'nope' in 'field list'"
    assert result["attempts"] == 1
    assert result["final_sql"] == "SELECT nope FROM products"
    assert result["error_history"][0]["code"] == 1054


def test_repaired_question_is_correct_and_records_attempts(monkeypatch):
    use_fakes(monkeypatch, ["SELECT nope FROM products", "SELECT `Product Name` FROM products"],
              rows=[("Product 26",)], error=unknown_column_error(), fail_times=1)

    result = evalcheck.evaluate_question("Best product?", GOLD, max_repairs=2)

    assert result["label"] == "correct"
    assert result["attempts"] == 2
    assert [entry["code"] for entry in result["error_history"]] == [1054]
    assert result["final_sql"] == "SELECT `Product Name` FROM products LIMIT 100"


def test_failed_repairs_keep_whole_history(monkeypatch):
    use_fakes(monkeypatch, ["SELECT nope FROM products"] * 3, error=unknown_column_error())

    result = evalcheck.evaluate_question("Best product?", GOLD, max_repairs=2)

    assert result["label"] == "sql_error"
    assert result["attempts"] == 3
    assert len(result["error_history"]) == 3


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


def record(run, question_id, difficulty, split, label, attempts=1, error_history=None):
    return {"run": run, "id": question_id, "difficulty": difficulty, "split": split,
            "label": label, "seconds": 1.0, "attempts": attempts,
            "error_history": error_history or []}


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


def test_summarize_repair_numbers_and_changes_vs_baseline():
    one_error = [{"sql": "x", "code": 1064, "message": "syntax"}]
    baseline = [
        record(1, "q1", "join", "dev", "sql_error"),
        record(1, "q2", "easy", "test", "correct"),
        record(1, "q3", "hard", "test", "wrong_result"),
    ]
    details = [
        record(1, "q1", "join", "dev", "correct", attempts=2, error_history=one_error),
        record(1, "q2", "easy", "test", "wrong_result"),
        record(1, "q3", "hard", "test", "wrong_result"),
    ]

    summary = evalcheck.summarize(details, "fake-model", "all", runs=1,
                                  max_repairs=2, baseline_details=baseline)

    assert summary["max_repairs"] == 2
    assert summary["needed_repair_per_run"] == [1]
    assert summary["fixed_by_repair_per_run"] == [1]
    assert summary["average_llm_calls_per_question"] == round(4 / 3, 2)
    assert summary["changed_vs_baseline"] == [
        {"id": "q1", "direction": "better",
         "baseline_labels": ["sql_error"], "new_labels": ["correct"]},
        {"id": "q2", "direction": "WORSE",
         "baseline_labels": ["correct"], "new_labels": ["wrong_result"]},
    ]
