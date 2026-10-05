"""Helpers for evaluating QueryMind.

- compare_results: compare the rows of a generated query with the gold rows
- evaluate_question: answer one question with querymind.answer_with_repair and label it
- summarize: turn all the labels into the numbers for the results/*.json summary
"""

import datetime
import itertools
import statistics
import time
from decimal import Decimal

from sqlalchemy.exc import DBAPIError

import querymind

# All possible labels, in the order we report them.
LABELS = [
    "correct",                # same rows as gold
    "correct_extra_columns",  # gold rows, plus some extra columns
    "wrong_result",           # the query ran but gave different rows
    "sql_error",              # MySQL refused or failed to run the query
    "unsafe_sql",             # our safety guard rejected the query
    "generation_error",       # the OpenAI call failed
]
CORRECT_LABELS = ["correct", "correct_extra_columns"]


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


def evaluate_question(question, gold_rows, max_repairs=2):
    """Answer one question with querymind.answer_with_repair (the same code path as the
    app), compare the rows with the gold rows and label the result.
    max_repairs=0 means no repairs, exactly like the baseline.
    Never raises: every problem becomes a label, so one failure can't stop the whole run."""
    result = {
        "final_sql": None,
        "label": None,
        "attempts": None,
        "error_history": [],
        "error_code": None,
        "error": None,
        "row_count": None,
        "first_rows": None,
        "seconds": None,
    }

    start = time.perf_counter()
    try:
        answer = querymind.answer_with_repair(question, max_repairs=max_repairs)
    except Exception as error:
        result["seconds"] = round(time.perf_counter() - start, 2)
        # answer_with_repair attaches what happened to the error it raises.
        result["final_sql"] = getattr(error, "sql", None)
        result["attempts"] = getattr(error, "attempts", None)
        result["error_history"] = getattr(error, "error_history", [])
        if isinstance(error, querymind.UnsafeSQLError):
            result["label"] = "unsafe_sql"
            result["error"] = str(error)
        elif isinstance(error, DBAPIError):
            result["label"] = "sql_error"
            result["error_code"], result["error"] = querymind.describe_sql_error(error)
        else:
            # Anything else comes from the LLM call (network, rate limit, ...).
            result["label"] = "generation_error"
            result["error"] = f"{type(error).__name__}: {error}"
        return result
    result["seconds"] = round(time.perf_counter() - start, 2)

    rows = answer["rows"]
    result["final_sql"] = answer["sql"]
    result["attempts"] = answer["attempts"]
    result["error_history"] = answer["error_history"]
    result["row_count"] = len(rows)
    result["first_rows"] = [[normalize_value(value) for value in row] for row in rows[:3]]

    comparison = compare_results(gold_rows, rows)
    if comparison == "exact":
        result["label"] = "correct"
    elif comparison == "extra_columns":
        result["label"] = "correct_extra_columns"
    else:
        result["label"] = "wrong_result"
    return result


def x_of_n(x, n):
    """Format like "21 of 30". A median of an even number of runs can be 20.5."""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return f"{x} of {n}"


def count_label(records, labels):
    return sum(1 for record in records if record["label"] in labels)


def breakdown(details, field, run_numbers):
    """Correct answers per run, grouped by a field such as "difficulty" or "split"."""
    groups = {}
    for record in details:
        groups.setdefault(record[field], []).append(record)

    result = {}
    for group, records in groups.items():
        per_run = [count_label([r for r in records if r["run"] == run], CORRECT_LABELS)
                   for run in run_numbers]
        size = len([r for r in records if r["run"] == run_numbers[0]])
        result[group] = {
            "correct_per_run": [x_of_n(count, size) for count in per_run],
            "median_correct": x_of_n(statistics.median(per_run), size),
        }
    return result


def compare_with_baseline(details, baseline_details):
    """List the questions whose labels differ from the baseline run, in either direction.
    Labels are compared run by run (run 1 with run 1, and so on)."""
    def labels_by_question(records):
        labels = {}
        for record in sorted(records, key=lambda r: r["run"]):
            labels.setdefault(record["id"], []).append(record["label"])
        return labels

    before = labels_by_question(baseline_details)
    after = labels_by_question(details)

    changes = []
    for question_id, new_labels in after.items():
        old_labels = before.get(question_id)
        if old_labels is None or old_labels == new_labels:
            continue
        old_correct = sum(1 for label in old_labels if label in CORRECT_LABELS)
        new_correct = sum(1 for label in new_labels if label in CORRECT_LABELS)
        if new_correct > old_correct:
            direction = "better"
        elif new_correct < old_correct:
            direction = "WORSE"
        else:
            direction = "label changed, same correctness"
        changes.append({
            "id": question_id,
            "direction": direction,
            "baseline_labels": old_labels,
            "new_labels": new_labels,
        })
    return changes


def summarize(details, model, split, runs, max_repairs=0, baseline_details=None):
    """Build the summary (e.g. results/repair_loop.json) from the per-question details.
    Each detail record needs at least: id, difficulty, split, run, label, seconds,
    attempts and error_history. If baseline_details is given, the questions whose
    label changed compared with the baseline are listed too."""
    run_numbers = list(range(1, runs + 1))
    by_run = {run: [r for r in details if r["run"] == run] for run in run_numbers}
    number_of_questions = len(by_run[1])

    correct_per_run = [count_label(by_run[run], CORRECT_LABELS) for run in run_numbers]

    # Questions that did not get the same label in every run.
    labels_by_question = {}
    for record in details:
        labels_by_question.setdefault(record["id"], []).append(record["label"])
    changed = [{"id": question_id, "labels": labels}
               for question_id, labels in labels_by_question.items()
               if len(set(labels)) > 1]

    # A question "needed a repair" if MySQL rejected its first SQL.
    # It was "fixed by repair" if it still ended up correct.
    needed_repair = [[r for r in by_run[run] if r["error_history"]] for run in run_numbers]

    summary = {
        "model": model,
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "split": split,
        "runs": runs,
        "max_repairs": max_repairs,
        "number_of_questions": number_of_questions,
        "correct_per_run": [x_of_n(c, number_of_questions) for c in correct_per_run],
        "median_correct": x_of_n(statistics.median(correct_per_run), number_of_questions),
        "exact_per_run": [count_label(by_run[run], ["correct"]) for run in run_numbers],
        "extra_columns_per_run": [count_label(by_run[run], ["correct_extra_columns"])
                                  for run in run_numbers],
        "by_difficulty": breakdown(details, "difficulty", run_numbers),
        "by_split": breakdown(details, "split", run_numbers),
        "label_counts": {label: count_label(details, [label]) for label in LABELS},
        "label_counts_per_run": [{label: count_label(by_run[run], [label]) for label in LABELS}
                                 for run in run_numbers],
        "needed_repair_per_run": [len(records) for records in needed_repair],
        "fixed_by_repair_per_run": [count_label(records, CORRECT_LABELS)
                                    for records in needed_repair],
        "average_llm_calls_per_question": round(
            statistics.mean(record["attempts"] or 0 for record in details), 2),
        "average_seconds_per_question": round(
            statistics.mean(record["seconds"] for record in details), 2),
        "changed_between_runs": changed,
    }
    if baseline_details is not None:
        summary["changed_vs_baseline"] = compare_with_baseline(details, baseline_details)
    return summary
