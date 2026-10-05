"""Tests for check_sql_is_safe. No OpenAI or MySQL needed."""

import pytest

from querymind import UnsafeSQLError, check_sql_is_safe


# (input SQL, SQL we expect back)
SAFE_CASES = [
    ("SELECT * FROM products LIMIT 5", "SELECT * FROM products LIMIT 5"),
    ("select * from products limit 5", "select * from products limit 5"),
    ("SELECT * FROM products", "SELECT * FROM products LIMIT 100"),
    ("SELECT * FROM products;", "SELECT * FROM products LIMIT 100"),
    ("  SELECT 1  ", "SELECT 1 LIMIT 100"),
    ("SELECT update_date FROM orders", "SELECT update_date FROM orders LIMIT 100"),
    ("SELECT created_at, last_updated FROM orders LIMIT 10",
     "SELECT created_at, last_updated FROM orders LIMIT 10"),
    ("SELECT `2017 Budgets` FROM `2017_budgets` WHERE `Product Name` = 'Product 12'",
     "SELECT `2017 Budgets` FROM `2017_budgets` WHERE `Product Name` = 'Product 12' LIMIT 100"),
    ("WITH t AS (SELECT 1 AS x) SELECT x FROM t", "WITH t AS (SELECT 1 AS x) SELECT x FROM t LIMIT 100"),
    ("SELECT COUNT(*) FROM customers", "SELECT COUNT(*) FROM customers LIMIT 100"),
]

UNSAFE_CASES = [
    "DROP TABLE x",
    "drop table x",
    "SELECT 1; DROP TABLE x",
    "SELECT 1; SELECT 2",
    "DELETE FROM customers",
    "UPDATE products SET `Product Name` = 'x'",
    "INSERT INTO products VALUES (99, 'x')",
    "TRUNCATE TABLE products",
    "ALTER TABLE products ADD COLUMN y INT",
    "CREATE TABLE y (id INT)",
    "GRANT ALL ON *.* TO 'bob'",
    "REPLACE INTO products VALUES (1, 'x')",
    "SELECT * FROM products -- WHERE 1",
    "SELECT * FROM products /* hidden */",
    "WITH t AS (SELECT 1) DELETE FROM products",
    "SHOW TABLES",
    "",
    "   ;  ",
]


@pytest.mark.parametrize("sql, expected", SAFE_CASES)
def test_safe_sql_is_allowed(sql, expected):
    assert check_sql_is_safe(sql) == expected


@pytest.mark.parametrize("sql", UNSAFE_CASES)
def test_unsafe_sql_is_rejected(sql):
    with pytest.raises(UnsafeSQLError):
        check_sql_is_safe(sql)


def test_check_is_idempotent():
    # answer_question and run_query both call the guard, so checking twice must not change anything.
    once = check_sql_is_safe("SELECT * FROM products")
    assert check_sql_is_safe(once) == once


def test_known_false_positive_blocked_word_in_string():
    # Documented limitation: the guard does not understand quotes, so a harmless
    # query is rejected because the text 'Drop Shipping' contains the word DROP.
    with pytest.raises(UnsafeSQLError):
        check_sql_is_safe("SELECT * FROM orders WHERE channel = 'Drop Shipping'")
