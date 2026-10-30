# Error analysis

Every incorrect answer, labelled by where it went wrong.

## Full agent – dev (0 of 3 wrong)


| id | type | expected | got | label | missing caveats |
|---|---|---|---|---|---|

## Agent without metrics layer – dev (2 of 3 wrong)

- missing caveat: 1
- refuse instead of answer at plan: 1

| id | type | expected | got | label | missing caveats |
|---|---|---|---|---|---|
| D001 | single_fact | answer | answer | missing caveat | provisional |
| D002 | single_fact | answer | refuse | refuse instead of answer at plan | provisional |

## Plain LLM (no data) – dev (3 of 3 wrong)

- refuse instead of answer: 2
- wrong values: 1

| id | type | expected | got | label | missing caveats |
|---|---|---|---|---|---|
| D001 | single_fact | answer | refuse | refuse instead of answer | provisional |
| D002 | single_fact | answer | refuse | refuse instead of answer | provisional |
| D003 | single_fact | answer | answer | wrong values |  |

