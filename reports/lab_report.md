# Day 08 Lab Report

## 1. Team / student

- Name: TODO
- Repo/commit: TODO
- Date: TODO

## 2. Architecture

The graph is `START -> intake -> classify -> conditional routing -> answer/clarify/risky_action/retry -> finalize -> END`.

Node roles:
- `intake`: normalize the raw query.
- `classify`: choose `simple`, `tool`, `missing_info`, `risky`, or `error` using keyword priority.
- `tool`: simulate a lookup or transient failure.
- `evaluate`: decide whether the tool output needs retry.
- `retry`: increment `attempt` and loop back to `tool` while under `max_attempts`.
- `risky_action` + `approval`: gate high-risk actions.
- `dead_letter`: capture exhausted retries.
- `finalize`: attach the final audit event before `END`.

State uses overwrite fields for current decision values and append-only reducers for audit trails (`messages`, `tool_results`, `errors`, `events`).

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| route | overwrite | current route only |
| attempt | overwrite | latest retry counter |
| max_attempts | overwrite | fixed retry budget |
| final_answer | overwrite | final response only |
| evaluation_result | overwrite | current retry gate result |
| messages | append | audit conversation/events |
| tool_results | append | preserve tool history |
| errors | append | preserve failure history |
| events | append | preserve node trace |

## 4. Scenario results

| Scenario | Expected route | Actual route | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | Yes | 0 | 0 |
| S02_tool | tool | tool | Yes | 0 | 0 |
| S03_missing | missing_info | missing_info | Yes | 0 | 0 |
| S04_risky | risky | risky | Yes | 0 | 2 |
| S05_error | error | error | Yes | 4 | 0 |
| S06_delete | risky | risky | Yes | 0 | 2 |
| S07_dead_letter | error | error | Yes | 2 | 0 |

## 5. Failure analysis

1. Retry or tool failure: `S05_error` exercises the retry loop. The tool emits a transient error, `evaluate` returns `needs_retry`, and the graph loops until the error condition clears.
2. Risky action without approval: `S04_risky` and `S06_delete` go through `risky_action -> approval` before the tool call, so unsafe actions do not bypass HITL.

## 6. Persistence / recovery evidence

The submission uses a persistent SQLite checkpointer (`checkpointer: sqlite`) with a per-scenario `thread_id`. Recovery evidence is recorded through state history after re-invoking the first scenario with the same `thread_id`; `resume_success` is set to `true` in the metrics report when state history is available.

## 7. Extension work

Completed extension work:
- SQLite persistence for checkpointing.
- Recovery probe using the same `thread_id`.
- Graph diagram can be exported from the compiled graph if needed for demo.

## 8. Improvement plan

If I had one more day, I would productionize the routing layer with an LLM classifier, add a real HITL approval UI, and replace the mock tool with an actual service integration.

## Metrics summary

- Total scenarios: 7
- Success rate: 100.00%
- Average nodes visited: 13.43
- Total retries: 6
- Total interrupts: 4
- Resume success: true

## Validation

- `pytest`: pass
- `run-scenarios`: pass
- `validate-metrics`: pass
