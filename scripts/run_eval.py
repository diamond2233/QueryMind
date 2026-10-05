"""Measure QueryMind on the gold questions in eval/questions.json.

For every question and every run: ask the LLM for SQL (querymind.generate_sql), run it
through the safety guard on the real database, compare its rows with the gold rows, and
label it. Writes a summary and a details file.

Usage (from the project folder):
    python scripts/run_eval.py                       # all 30 questions, 3 runs
    python scripts/run_eval.py --split dev --runs 1  # quick check on the dev set
"""

import argparse
import json
import os
import sys

# Let this script import querymind.py and evalcheck.py from the project folder.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import evalcheck
import querymind

QUESTIONS_FILE = os.path.join(PROJECT_DIR, "eval", "questions.json")


def parse_args():
    parser = argparse.ArgumentParser(description="Measure QueryMind on the gold questions.")
    parser.add_argument("--runs", type=int, default=3, help="how many times to ask each question")
    parser.add_argument("--split", choices=["all", "dev", "test"], default="all")
    parser.add_argument("--output", default="results/baseline.json", help="summary file")
    return parser.parse_args()


def load_questions(split):
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        questions = json.load(f)
    if split != "all":
        questions = [q for q in questions if q["split"] == split]
    return questions


def save_json(path, data):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    args = parse_args()
    questions = load_questions(args.split)
    model = querymind.load_config()["openai_model"]
    print(f"Model {model}, {len(questions)} questions, {args.runs} runs")

    # Run every gold query once. If one fails, stop: fix it with scripts/verify_gold.py first.
    gold_rows = {}
    for q in questions:
        gold_rows[q["id"]] = evalcheck.run_sql_rows(q["gold_sql"])

    details = []
    for run in range(1, args.runs + 1):
        for q in questions:
            result = evalcheck.evaluate_question(q["question"], gold_rows[q["id"]])
            record = {
                "run": run,
                "id": q["id"],
                "difficulty": q["difficulty"],
                "split": q["split"],
                "question": q["question"],
                **result,
                "gold_row_count": len(gold_rows[q["id"]]),
                "gold_first_rows": [[evalcheck.normalize_value(v) for v in row]
                                    for row in gold_rows[q["id"]][:3]],
            }
            details.append(record)
            print(f"run {run}  {q['id']}  {record['label']:<22} {record['seconds']}s")

    summary = evalcheck.summarize(details, model, args.split, args.runs)

    details_path = os.path.splitext(args.output)[0] + "_details.json"
    save_json(args.output, summary)
    save_json(details_path, details)

    print()
    print("Correct per run:", ", ".join(summary["correct_per_run"]))
    print("Median correct: ", summary["median_correct"])
    print("Label counts:   ", summary["label_counts"])
    print(f"Saved {args.output} and {details_path}")


if __name__ == "__main__":
    main()
