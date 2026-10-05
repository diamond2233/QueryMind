# Q3 explained: measuring the current system

The goal of Q3 is to **measure**, not to improve. Nothing in `querymind.py` changed: same
prompts, same model, same temperature. We only added a way to grade it.

## What's new

| File | What it does |
|---|---|
| `evalcheck.py` | `compare_results` compares two query results. `evaluate_question` asks the model for SQL for one question, runs it and labels it. `summarize` turns all the labels into numbers. |
| `scripts/run_eval.py` | Runs every gold question (3 times by default) and writes the results. |
| `results/baseline.json` | The summary: how many correct, by difficulty and by split, label counts, speed. |
| `results/baseline_details.json` | One entry per question per run: the generated SQL, its label, any error, and its first rows next to the gold rows. |

## What execution accuracy is

**Execution accuracy** = how many questions the model got right, where "right" means:
*when we run the model's SQL, we get the same rows as when we run the gold SQL.*

It is written like "21 of 30". That's like an exam score: 30 questions, 21 answered correctly.

Every attempt gets exactly one label:

| Label | Meaning |
|---|---|
| `correct` | Same rows as the gold query. |
| `correct_extra_columns` | The gold rows are there, plus some extra columns (see below). Counted as correct. |
| `wrong_result` | The SQL ran fine but gave different rows. |
| `sql_error` | MySQL could not run the SQL, e.g. a column name that doesn't exist. We keep MySQL's error code and message. |
| `unsafe_sql` | Our safety guard refused to run it. |
| `generation_error` | The OpenAI call itself failed (network, rate limit...). It's recorded and the run continues. |

## Why we compare results, not SQL text

The same question can be answered by many different SQL queries. For example:

```sql
SELECT COUNT(*) FROM customers
SELECT COUNT(`Customer Index`) FROM customers
```

Both give 175, so both are correct, even though the text is different. Comparing the text
would wrongly mark the second one as wrong. The user only sees the answer, so the answer
(the rows) is what we grade.

Before comparing, we tidy up each value so tiny differences don't count:
numbers are rounded to 2 decimals (so `298083669.99999994` equals `298083670`, and `9540`
equals `Decimal('9540')`), spaces around text are removed, dates become text like
`2024-01-31`, and `None` stays `None`. Column names are ignored, so `SUM(x)` and `AS total`
don't matter.

## Why row order is ignored, and what that can hide

We sort both results before comparing, so the order of rows doesn't matter. This is needed
because SQL gives no promise about order unless the query says `ORDER BY`. For "which
sales channels do we sell through?", `Wholesale, Distributor, Export` and
`Export, Wholesale, Distributor` are the same correct answer.

**What it can hide:** for questions where the order *is* the answer, a wrong order still
counts as correct. For "Who are our top 3 customers by total sales?", if the model returns
the right 3 customers but ranked 3rd, 2nd, 1st, we still mark it correct. This is a known
simplification. Our test set has only a few such questions, and the most common ranking
mistake (choosing the wrong top 3) is still caught, because the rows themselves differ.

## What "extra columns" means

Sometimes the model answers the question *and* shows its working:

| Gold SQL returns | Model SQL returns |
|---|---|
| `Aibox Company` | `Aibox Company, 139` |

The customer is right. The extra `139` (the number of order lines) is just extra
information. We call this `correct_extra_columns` and count it as correct, because a person
reading it would get the right answer. We still report it separately, so we can see how
often it happens.

The check: if the model's result has *more* columns than gold, we try every way of picking
the same number of columns as gold (in any order). If one of those picks gives exactly the
gold rows, it's `correct_extra_columns`. Fewer columns than gold, or extra columns with
wrong values, is `wrong_result`.

## Why we run 3 times

Even with temperature 0, OpenAI models don't always give exactly the same answer twice. A
question can be right on one run and wrong on the next. If we ran only once, we might be
lucky or unlucky. So we run every question 3 times and report:

- the score of each run, e.g. "21 of 30, 22 of 30, 21 of 30";
- the **median** (the middle value), which is not thrown off by one lucky or unlucky run;
- the list of questions whose label **changed between runs**. These are the "unstable"
  questions, which are often the most interesting ones to look at.

## One detail: why the evaluation doesn't use `run_query` directly

`querymind.run_query` returns the result as **text** made by LangChain, e.g.
`"[(Decimal('67015.8118'),)]"`. Long values are cut short, and an empty result is just `''`.
That's fine for the LLM to read, but we can't reliably compare it value by value.

So in Q3, `evalcheck.run_sql_rows` did exactly what `run_query` does (the same
`check_sql_is_safe` guard first, then the same database connection) but asked for real rows.

**Update in Q4:** this is no longer needed. `run_query` itself now returns real rows, and
both the app and the evaluation go through the same function,
`querymind.answer_with_repair`. See `docs/repair-loop.md`.

## How to run the evaluation yourself

1. Make sure `.env` is filled in (OpenAI key, read-only MySQL user).
2. Check the gold queries still work: `python scripts/verify_gold.py`
3. Run the evaluation:

   ```bash
   python scripts/run_eval.py --runs 3
   ```

   It prints one line per question per run, then the summary. 30 questions × 3 runs = 90
   OpenAI calls, which costs a few cents.

4. Open `results/baseline.json` for the numbers and `results/baseline_details.json` to see
   exactly what the model wrote for each question.

Useful options:

```bash
python scripts/run_eval.py --split dev --runs 1                 # quick: 10 dev questions, once
python scripts/run_eval.py --output results/my_try.json         # don't overwrite the baseline
```

The tests for all of this use a fake LLM and a fake database, so they cost nothing:

```bash
python -m pytest -v
```
