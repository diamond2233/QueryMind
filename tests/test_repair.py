"""Tests for the repair loop in querymind.answer_with_repair, with a fake LLM and a fake
database. No real OpenAI or MySQL calls are made."""

import pymysql
import pytest
import sqlalchemy.exc
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import querymind

BAD_SQL = "SELECT SUM(Line Total) FROM sales_order"
GOOD_SQL = "SELECT SUM(`Line Total`) FROM sales_order"
SYNTAX_ERROR = "You have an error in your SQL syntax near 'Total) FROM sales_order'"


def mysql_error(code, message):
    """Build the same kind of error SQLAlchemy raises when MySQL rejects a query."""
    return sqlalchemy.exc.ProgrammingError("SQL", {}, pymysql.err.ProgrammingError(code, message))


class FakeCursor:
    def keys(self):
        return ["total"]

    def fetchall(self):
        return [(5516847.0,)]


class FakeDB:
    """Raises `error` for any SQL containing 'Line Total' without backticks; otherwise
    returns one row. Remembers every SQL it was asked to run."""

    def __init__(self, error):
        self.error = error
        self.executed = []

    def get_table_info(self):
        return "CREATE TABLE sales_order (`Line Total` DOUBLE)"

    def run(self, sql, fetch="all"):
        self.executed.append(sql)
        if "(Line Total)" in sql:
            raise self.error
        return FakeCursor()


def use_fakes(monkeypatch, llm_replies, error=None):
    """Install a fake DB and a fake LLM, and count calls to repair_sql.
    The fake LLM gives its replies in order: first the generated SQL, then each repair."""
    fake_db = FakeDB(error or mysql_error(1064, SYNTAX_ERROR))
    monkeypatch.setattr(querymind, "get_db", lambda: fake_db)
    fake_llm = FakeListChatModel(responses=llm_replies)
    monkeypatch.setattr(querymind, "get_llm", lambda: fake_llm)

    repair_calls = []
    real_repair_sql = querymind.repair_sql

    def recording_repair_sql(question, schema, failed_sql, error_message):
        repair_calls.append({"failed_sql": failed_sql, "error_message": error_message})
        return real_repair_sql(question, schema, failed_sql, error_message)

    monkeypatch.setattr(querymind, "repair_sql", recording_repair_sql)
    return fake_db, repair_calls


def test_syntax_error_is_repaired_on_second_attempt(monkeypatch):
    fake_db, repair_calls = use_fakes(monkeypatch, [BAD_SQL, GOOD_SQL])

    result = querymind.answer_with_repair("Total sales?", max_repairs=2)

    assert result["sql"] == GOOD_SQL + " LIMIT 100"
    assert result["rows"] == [(5516847.0,)]
    assert result["attempts"] == 2
    assert result["error_history"] == [{"sql": BAD_SQL, "code": 1064, "message": SYNTAX_ERROR}]
    # The model was told the exact MySQL error, with its code.
    assert repair_calls == [{"failed_sql": BAD_SQL, "error_message": "1064: " + SYNTAX_ERROR}]
    assert len(fake_db.executed) == 2


def test_loop_stops_after_max_repairs(monkeypatch):
    fake_db, repair_calls = use_fakes(monkeypatch, [BAD_SQL] * 5)

    with pytest.raises(sqlalchemy.exc.DBAPIError) as caught:
        querymind.answer_with_repair("Total sales?", max_repairs=2)

    # 1 generation + 2 repairs, then it gives up and raises the last error.
    assert len(repair_calls) == 2
    assert len(fake_db.executed) == 3
    assert caught.value.attempts == 3
    assert [entry["code"] for entry in caught.value.error_history] == [1064, 1064, 1064]


def test_guard_rejection_is_not_repaired(monkeypatch):
    fake_db, repair_calls = use_fakes(monkeypatch, ["SELECT 1; DROP TABLE x", GOOD_SQL])

    with pytest.raises(querymind.UnsafeSQLError) as caught:
        querymind.answer_with_repair("Total sales?", max_repairs=2)

    assert repair_calls == []
    assert fake_db.executed == []
    assert caught.value.attempts == 1


def test_unsafe_repair_is_rejected_and_not_executed(monkeypatch):
    # The guard also checks every repaired query.
    fake_db, repair_calls = use_fakes(monkeypatch, [BAD_SQL, "DROP TABLE sales_order"])

    with pytest.raises(querymind.UnsafeSQLError):
        querymind.answer_with_repair("Total sales?", max_repairs=2)

    assert len(repair_calls) == 1
    assert fake_db.executed == [BAD_SQL + " LIMIT 100"]


def test_max_repairs_zero_behaves_like_before(monkeypatch):
    fake_db, repair_calls = use_fakes(monkeypatch, [BAD_SQL, GOOD_SQL])

    with pytest.raises(sqlalchemy.exc.DBAPIError) as caught:
        querymind.answer_with_repair("Total sales?", max_repairs=0)

    assert repair_calls == []
    assert len(fake_db.executed) == 1
    assert caught.value.attempts == 1
    assert caught.value.sql == BAD_SQL


def test_max_repairs_zero_with_good_sql_runs_once(monkeypatch):
    fake_db, repair_calls = use_fakes(monkeypatch, [GOOD_SQL])

    result = querymind.answer_with_repair("Total sales?", max_repairs=0)

    assert result["attempts"] == 1
    assert result["error_history"] == []
    assert repair_calls == []


def test_non_repairable_mysql_error_is_not_repaired(monkeypatch):
    lost_connection = sqlalchemy.exc.OperationalError(
        "SQL", {}, pymysql.err.OperationalError(2013, "Lost connection to MySQL server"))
    fake_db, repair_calls = use_fakes(monkeypatch, [BAD_SQL, GOOD_SQL], error=lost_connection)

    with pytest.raises(sqlalchemy.exc.DBAPIError) as caught:
        querymind.answer_with_repair("Total sales?", max_repairs=2)

    assert repair_calls == []
    assert caught.value.error_history[0]["code"] == 2013
