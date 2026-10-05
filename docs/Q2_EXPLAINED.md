# Q2 explained: the gold test set

## What's new

| File | What it is |
|---|---|
| `eval/questions.json` | 30 business questions about our database, each with the correct SQL. |
| `scripts/verify_gold.py` | Runs every correct SQL on the real database and prints the result, so a human can check it. |

Nothing here calls OpenAI. This is the "answer key" we will later grade the model against.

## What a gold query is

A **gold query** is the SQL we *know* is correct for a question, the way a teacher's answer
key is correct for an exam. Each entry in `questions.json` looks like this:

```json
{
  "id": "q01",
  "difficulty": "easy",
  "question": "What was the 2017 budget for Product 5?",
  "gold_sql": "SELECT `2017 Budgets` FROM `2017_budgets` WHERE `Product Name` = 'Product 5'",
  "split": "dev"
}
```

Later, we give the model only the `question`, let it write its own SQL, run both, and compare
the **results**. If they match, the model got it right. We compare results, not SQL text,
because two different SQL queries can give the same correct answer.

The 30 questions are mixed so we can see *where* the model struggles:

- **easy (8):** one table, a simple lookup or filter.
- **medium (8):** one table with `COUNT`/`SUM`/`AVG`, `GROUP BY`, `ORDER BY` or a date filter.
- **join (8):** two tables joined together.
- **hard (6):** three or more tables, or `HAVING`, a subquery, or a ranking.

The questions are worded like a business user would ask ("What were our total sales in
2023?"), not by repeating column names (`SUM(Line Total)`), because that's how real users ask.

## Why a human must check every gold query

If the answer key is wrong, every grade is wrong. A wrong gold query would mark the model
wrong when it was right, or right when it was wrong, and we'd never notice. A computer can
tell us that a query *runs*, but not that it answers *the question that was asked*. Only a
human can check that.

While writing these questions I found real traps in our data, which is exactly why checking
matters:

- **Order numbers are not real order IDs.** `sales_order` has 64,104 rows but only 10,684
  different order numbers, and the same number appears on different dates for different
  customers. So "how many orders?" has no single correct answer. The questions say
  **order lines** (rows) instead, and none of them uses order numbers.
- **Some place names repeat.** Center, Perry and Wayne each appear twice in Indiana, so those
  places are never used in a question. Other places are always given with their state, as in
  "Auburn, Alabama".
- **Ties.** "Which product sold the most?" only has one answer if there is no tie for first
  place. Every "top" question was checked: the closest is "most units overall", where
  Product 26 sold 50,364 units against Product 25's 50,358. That's close, but it's not a tie.
- **"Region" means two things.** The `regions` table is really a list of *places* (cities,
  towns), while `state_regions` has the four *parts of the country* (South, West, Northeast,
  Midwest). The questions mostly say "places" or "part of the country" so there is no
  confusion. One question, q03 ("Which states belong to the Northeast region?"), does use the
  word "region". That's fine, because "Northeast" only exists as a part of the country, never
  as a place, so the question can only be read one way.
- **Sales data is 2021 to February 2025, budgets are only for 2017.** No question compares
  budget with sales, because those years don't overlap.

`verify_gold.py` helps with the human check. It also passes every gold query through the same
safety guard as the app, runs it as the read-only user, and flags any query that fails or
returns no rows. A gold query that returns nothing can't be used to grade anything.

## Why we split the questions into dev and test

- **dev (10 questions):** the "practice" set. We may look at these while improving the
  prompts and the code, as often as we like.
- **test (20 questions):** the "final exam". We only use them to measure, never to tune.

If we tuned the prompt until all 30 questions were right, a high score would only show that
the prompt is good at *these exact questions*, not at new ones. That's like a student who has
seen the exam beforehand. Keeping the test set untouched gives an honest score. The dev set
has questions of every difficulty (3 easy, 3 medium, 2 join, 2 hard), so practice covers
everything.

## How to add a new question yourself

1. **Look at the real data first.** For example, to ask about a customer, check the name exists:

   ```sql
   SELECT `Customer Names` FROM customers WHERE `Customer Names` LIKE 'Geiss%';
   ```

2. **Write the question like a business user would**, and make sure it has exactly one
   answer. Ask yourself: could someone read it two ways? Could there be a tie?
3. **Write the gold SQL** and run it yourself in MySQL to check the result makes sense.
4. **Add an entry** to the end of `eval/questions.json` with the next free id (e.g. `"q31"`),
   a `difficulty` (`easy`, `medium`, `join` or `hard`) and a `split`. New questions normally go
   in `test`. Use `dev` only if you plan to use it while tuning.
5. **Run the check** and read your question's output by hand:

   ```bash
   python scripts/verify_gold.py
   ```

   It must end with "All N gold queries passed the guard and returned rows."

Two small things to know when writing gold SQL. The guard rejects the words `INSERT`,
`UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REPLACE`, and the
characters `--`, `/*`, `#` and `;` (except at the end), even inside text. It also adds
`LIMIT 100` when there is no `LIMIT`, so a gold query should return fewer than 100 rows.
