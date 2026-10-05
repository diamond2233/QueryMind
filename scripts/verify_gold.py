"""Check every gold query in eval/questions.json against the real database.

For each question it prints the id, difficulty, question, SQL, number of rows and the
first 3 rows, so a human can check by hand that the SQL really answers the question.
It does not call OpenAI.

Usage (from the project folder):
    python scripts/verify_gold.py
"""

import json
import os
import sys

# Let this script import querymind.py from the project folder (one level up).
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import querymind

QUESTIONS_FILE = os.path.join(PROJECT_DIR, "eval", "questions.json")


def load_questions():
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def run_gold_sql(sql):
    """Run one gold query through querymind.run_query, the same function the app uses
    (safety guard first). Returns (the SQL that ran, list of rows)."""
    safe_sql, columns, rows = querymind.run_query(sql)
    return safe_sql, rows


def main():
    questions = load_questions()
    problems = []

    for q in questions:
        print("=" * 80)
        print(f"{q['id']}  [{q['difficulty']}, {q['split']}]  {q['question']}")
        try:
            safe_sql, rows = run_gold_sql(q["gold_sql"])
        except Exception as error:
            print("SQL: ", q["gold_sql"])
            print("FAILED:", error)
            problems.append((q["id"], f"failed: {error}"))
            continue

        print("SQL: ", safe_sql)
        print("Rows:", len(rows))
        for row in rows[:3]:
            print("     ", tuple(row))
        if not rows:
            print("NO ROWS")
            problems.append((q["id"], "returned no rows"))

    print("=" * 80)
    if problems:
        print(f"{len(problems)} of {len(questions)} gold queries have problems:")
        for question_id, reason in problems:
            print(f"  {question_id}: {reason}")
        sys.exit(1)
    print(f"All {len(questions)} gold queries passed the guard and returned rows.")


if __name__ == "__main__":
    main()
