# Q4 explained: the repair loop

## The problem we saw in the baseline

The baseline (Q3) got **26 of 30** questions right. Of the 4 failures, 3 (q17, q22, q25)
were the same small mistake. The model wrote

```sql
SELECT SUM(Line Total) ...
```

but the column is called `Line Total`, **with a space**. In MySQL a name with a space must
be wrapped in backticks: `` `Line Total` ``. Without them MySQL stops with
error **1064** ("You have an error in your SQL syntax").

The interesting part: MySQL's error message says exactly where the problem is. So if we
show the model its own SQL *and* the error, it can usually fix it. That's the repair loop.

## What changed in the code

| Function | What it does |
|---|---|
| `run_query(sql)` | Safety guard, then run. Now returns `(sql that ran, column names, rows)` with **real rows** (Python tuples), not LangChain's text. |
| `answer_with_repair(question, max_repairs=2)` | The **one** path from question to rows: generate SQL, guard, run, and repair MySQL errors. Used by the app *and* by the evaluation. |
| `repair_sql(question, schema, failed_sql, error_message)` | Asks the model to fix SQL that MySQL rejected. Its prompt is in the constant `REPAIR_TEMPLATE`. |
| `answer_question(question)` | Calls `answer_with_repair`, then writes the English answer (same answer prompt as before). |

Before Q4, the evaluation had its own copy of "guard + run" (`evalcheck.run_sql_rows`).
Now everything goes through `answer_with_repair`, so **what we measure is exactly what the
app does**. `verify_gold.py` uses `run_query` too.

## How the loop works, step by step

1. The model writes SQL for the question, using the same prompt as always.
2. The **safety guard** checks it. If the guard says no, we stop and raise `UnsafeSQLError`.
3. MySQL runs it. If it works, we're done: return the rows.
4. If MySQL says the SQL is wrong (error 1064 syntax, 1054 unknown column, 1146 unknown
   table, and similar: see `REPAIRABLE_ERROR_CODES`), we remember the error in
   `error_history` and call `repair_sql`. It gives the model:
   - the question and the schema,
   - the SQL that failed,
   - the **exact MySQL error**, e.g. `1064: You have an error ... near 'Total) AS ...'`,
   - the instruction to wrap every table and column name in backticks and return only SQL.
5. The repaired SQL goes back to step 2. **The guard checks every repaired query too.**
6. At most `max_repairs` repairs (default 2). If it still fails after the last one, the
   last error is raised.

`attempts` counts how many times the model wrote SQL: 1 means it worked first time,
2 means one repair was needed.

`max_repairs=0` means "never repair", which is exactly how the app behaved before. We
checked this: with `--max-repairs 0`, all 90 labels (30 questions × 3 runs) were the same
as the baseline.

## Why only database errors are repaired

- **Guard rejections (`UnsafeSQLError`) are never repaired.** If the guard blocks a query,
  asking the model to "fix" it would really mean asking it to find a way *around* our
  safety check. The guard must be a wall, not a puzzle to solve.
- **OpenAI errors** (network down, rate limit) aren't the SQL's fault. Retrying with a
  "fix this SQL" prompt makes no sense.
- **Other database errors** like "lost connection" (2013) or "access denied" aren't mistakes
  in the SQL either, so they're not in `REPAIRABLE_ERROR_CODES`.
- **Wrong results can't be repaired**, see q30 below.

## Why q30 can't be fixed this way

q30 asks: *"For each sales channel, which product brought in the most sales?"* The model
wrote a query that is **valid SQL**. It runs without any error, but it returns all 90
channel–product pairs instead of only the top product per channel.

The repair loop only starts when MySQL reports an error. Here there is no error: MySQL
happily runs the query. The program has no way to know the answer is wrong, because the
only thing that knows the right answer is our gold query, and the app doesn't have it.
Fixing this kind of mistake needs a better first prompt or a better model, not a repair.

## Results

All numbers come from `results/baseline.json` and `results/repair_loop.json` (3 runs each,
`gpt-4.1-mini`):

| | Baseline (no repairs) | With up to 2 repairs |
|---|---|---|
| **Overall** | **26 of 30** | **29 of 30** |
| easy | 8 of 8 | 8 of 8 |
| medium | 8 of 8 | 8 of 8 |
| join | 6 of 8 | 8 of 8 |
| hard | 4 of 6 | 5 of 6 |
| dev | 8 of 10 | 10 of 10 |
| test | 18 of 20 | 19 of 20 |
| `sql_error` (all runs) | 9 | 0 |

- Fixed: q17, q22, q25, in all 3 runs. **No question got worse.**
- Still wrong: q30 (as expected).
- Repairs were needed 4, 2 and 3 times in the three runs, and every repair worked on the
  first try. On average the model was called 1.1 times per question for SQL.

Something we learned: the model's *first* SQL is not always the same between runs. In run 1,
q13 first came out without backticks too (`Warehouse Code`) and was repaired. In run 2, q25
came out right first time. Without the repair loop these random slips would sometimes turn
a correct question into a wrong one.

## How to run the evaluation yourself

```bash
# with repairs (the default: up to 2)
python scripts/run_eval.py --runs 3 --output results/repair_loop.json

# without repairs: behaves like the baseline
python scripts/run_eval.py --runs 3 --max-repairs 0 --output results/repair0_check.json
```

Each run prints one line per question with its label and `attempts`, then a summary,
including **"Changed vs baseline"**: which questions got better or worse compared with
`results/baseline_details.json`. If a question got worse it prints a `WARNING` line.

Without `--output`, results go to `results/latest.json`, so the committed baseline is never
overwritten by accident.

The tests use a fake LLM and a fake database (no cost):

```bash
python -m pytest -v
```

`tests/test_repair.py` checks that a syntax error is repaired on the second attempt, that
the loop stops after `max_repairs`, that guard rejections are never repaired, that a
repaired query is checked by the guard again, and that `max_repairs=0` behaves like the
old code.
