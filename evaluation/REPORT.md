# Evaluation report

Backend `local` · 500 records · 0.18s wall clock · regenerate with `python evaluation/run_eval.py`

## Scores

| measure | result | what it means |
| --- | --- | --- |
| Fact recall | 100.0% | corrections that produced a dictionary entry |
| Fact direction | 100.0% | learned the correction, not the error |
| Preference activation | 100.0% | explicit rules that became active at once |
| Observed, not applied | 100.0% | inferred rules correctly held below the promotion gate |
| Refusal | 100.0% | sensitive and private utterances stored as nothing |
| Reminder capture | 100.0% | reminders kept as episodes, not rules |
| False facts | 0 | dictionary entries invented from ordinary speech |
| False preferences | 0 | rules invented from ordinary speech |
| Retrieval | 100.0% | anchors ranked first, and filter-only queries returning only valid results |
| End-to-end | 100.0% | Hey Kivi cases behaving as specified |

## Cost, latency and growth

- ingest latency p50 **0.21 ms**, p95 **0.37 ms**, max 1.34 ms
- database **5,009,104 bytes** after 500 records (**10018.2 bytes/record**)
- model calls **0**, tokens in/out 0/0, cost **$0.0**
- memory after the run: `fact/active` 10, `preference/active` 13, `episode/active` 490

## End-to-end cases

| case | intent | status | passed | trace |
| --- | --- | --- | --- | --- |
| `chain_slack_5pm` | find_dictation | found_and_reshaped | pass | `tr_d3dea46c666b` |
| `find_plain` | find_dictation | ambiguous | pass | `tr_3677d994b9cd` |
| `find_impossible` | find_dictation | ambiguous | pass | `tr_f5a1d516533a` |
| `recall_rules` | recall | answered | pass | `tr_86a7ca87ca6d` |
| `recall_spelling` | recall | answered | pass | `tr_97434b9f952e` |
| `remember_new` | remember | remembered | pass | `tr_1bb28d2ea997` |
| `remember_refused` | remember | declined | pass | `tr_3cebf9e32bb3` |
| `forget_rule` | forget | ambiguous | pass | `tr_4d5e6612cec4` |
| `reshape_with_selection` | reshape | drafted | pass | `tr_b6256c1e6bcf` |
| `reshape_without_selection` | reshape | ambiguous | pass | `tr_7e1d8daf8573` |
| `draft_named` | draft_message | drafted | pass | `tr_def4f1b4c08b` |
| `ambiguous_referent` | draft_message | ambiguous | pass | `tr_6d79dbed9ca8` |
| `nonsense` | None | unclear | pass | `tr_d980a4e4e49b` |

Open any trace at `/api/trace/<id>` while the app is running, or find it in `evaluation/results.json` under `end_to_end[].trace_steps`.
