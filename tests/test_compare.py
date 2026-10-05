"""Tests for evalcheck.compare_results. No OpenAI or MySQL needed."""

import datetime
from decimal import Decimal

from evalcheck import compare_results, normalize_value


def test_same_rows_are_exact():
    assert compare_results([("Product 26",)], [("Product 26",)]) == "exact"


def test_float_tolerance_two_decimals():
    # MySQL float sums are often a tiny bit off; we round to 2 decimals.
    assert compare_results([(298083669.99999994,)], [(298083670.0,)]) == "exact"


def test_bigger_float_difference_is_different():
    assert compare_results([(10.0,)], [(10.02,)]) == "different"


def test_row_order_is_ignored():
    gold = [("Wholesale",), ("Distributor",), ("Export",)]
    generated = [("Export",), ("Wholesale",), ("Distributor",)]
    assert compare_results(gold, generated) == "exact"


def test_decimal_vs_float_vs_int():
    assert compare_results([(Decimal("67015.8118"),)], [(67015.81,)]) == "exact"
    assert compare_results([(9540,)], [(Decimal("9540"),)]) == "exact"


def test_none_values():
    assert compare_results([(None, "a")], [(None, "a")]) == "exact"
    assert compare_results([(None,)], [(0,)]) == "different"


def test_strings_are_stripped():
    assert compare_results([("Urban County",)], [("Urban County ",)]) == "exact"


def test_dates_become_iso_text():
    assert normalize_value(datetime.date(2024, 1, 31)) == "2024-01-31"
    assert compare_results([("2024-01-31",)], [(datetime.date(2024, 1, 31),)]) == "exact"


def test_extra_column_is_extra_columns_not_exact():
    gold = [("Aibox Company",)]
    generated = [("Aibox Company", 139)]
    assert compare_results(gold, generated) == "extra_columns"


def test_extra_columns_in_any_order():
    gold = [("South", 16), ("West", 12)]
    generated = [(12, "x", "West"), (16, "x", "South")]
    assert compare_results(gold, generated) == "extra_columns"


def test_extra_columns_with_wrong_values_is_different():
    assert compare_results([("Aibox Company",)], [("State Ltd", 139)]) == "different"


def test_wrong_value_is_different():
    assert compare_results([("Product 26",)], [("Product 25",)]) == "different"


def test_different_row_count_is_different():
    gold = [("Product 25",), ("Product 26",)]
    assert compare_results(gold, [("Product 25",)]) == "different"
    assert compare_results(gold, gold + [("Product 14",)]) == "different"


def test_fewer_columns_than_gold_is_different():
    gold = [("South", 16), ("West", 12)]
    generated = [(16,), (12,)]
    assert compare_results(gold, generated) == "different"


def test_empty_result_is_different():
    assert compare_results([("TX",)], []) == "different"
