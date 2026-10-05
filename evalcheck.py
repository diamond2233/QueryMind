"""Helpers for evaluating QueryMind: compare the rows of a generated query with the gold rows.

No OpenAI and no database needed for anything in this file.
"""

import datetime
import itertools
from decimal import Decimal


def normalize_value(value):
    """Make one value comparable:
    - numbers (int, float, Decimal) -> float rounded to 2 decimals, so 9540, 9540.0 and
      Decimal('9540') are all equal, and 298083669.99999994 equals 298083670.0
    - strings -> surrounding spaces removed
    - dates and datetimes -> ISO text like '2024-01-31'
    - None stays None
    """
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return round(float(value), 2)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value)


def normalize_rows(rows):
    """Normalize every value and sort the rows, so row order does not matter.

    Known simplification: because we sort, a query that returns the right rows in the
    WRONG order (e.g. "top 3 customers" listed 3rd, 2nd, 1st) still counts as correct.
    We sort by the text form of each row so that mixed types (like None and numbers)
    can be sorted without errors.
    """
    normalized = [tuple(normalize_value(value) for value in row) for row in rows]
    return sorted(normalized, key=repr)


def column_count(rows):
    return len(rows[0]) if rows else 0


def compare_results(gold_rows, generated_rows):
    """Compare two query results, ignoring row order and column names.

    Returns:
    - "exact":         same rows (after normalizing)
    - "extra_columns": the generated result has MORE columns than gold, and picking some
                       of its columns (in some order) gives exactly the gold rows
    - "different":     anything else
    """
    gold = normalize_rows(gold_rows)
    generated = normalize_rows(generated_rows)

    if generated == gold:
        return "exact"

    gold_width = column_count(gold)
    generated_width = column_count(generated)
    if len(generated) == len(gold) and generated_width > gold_width > 0:
        # Try every way of choosing gold_width columns from the generated result.
        # e.g. gold has 1 column, generated has 3: try column 0, 1 and 2 on its own.
        for chosen in itertools.permutations(range(generated_width), gold_width):
            picked = [tuple(row[i] for i in chosen) for row in generated]
            if sorted(picked, key=repr) == gold:
                return "extra_columns"

    return "different"
