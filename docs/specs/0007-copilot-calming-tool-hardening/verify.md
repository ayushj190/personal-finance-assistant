# Verify: Copilot Calming & Tool Hardening · spec 0007 · updated 2026-10-11
_Steps derived from spec 0007 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [x] Open application and inspect copilot sidebar → verify copilot is completely quiet with no automatic inference tasks running → AC-1
- [x] Trigger background sync in app → verify copilot chat history and sidebar remain silent with zero unprompted messages → AC-1
- [x] Stop Ollama (`ollama stop` or disconnect) and submit a prompt in copilot → verify sidebar immediately displays friendly notice asking you to run `ollama serve` without spinning a failing task → AC-2
- [x] Start Ollama and click the Assess Risk button under Actions → verify explicit user prompt bubble appears in chat before assistant begins answering → AC-6
- [x] Ask copilot for spending breakdown on an empty database → verify tool returns friendly guidance explaining that no transactions exist and suggesting a statement import → AC-5
- [x] Trigger a forced tool error or database lock → verify assistant explains the issue politely and provides a collapsible troubleshooting details card → AC-4

## Commands
- [x] `.\.venv\Scripts\pytest -v tests/test_copilot_calming.py` → all tests pass verifying on demand behavior, authorizer enforcement, error recovery, and parameter sanitization → AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7
- [x] `.\.venv\Scripts\pytest tests/test_copilot_calming.py -k test_connect_readonly_denies_writes` → confirms SQLite engine authorizer blocks write queries → AC-3
- [x] `.\.venv\Scripts\pytest` → full test suite passes with zero regressions → AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7

## Acceptance-criteria coverage
- AC-1: Pure on demand execution and silent background sync covered by UI steps and `test_copilot_on_demand_execution`
- AC-2: Upfront Ollama health check covered by UI steps and `test_ollama_offline_heartbeat_notice`
- AC-3: Dedicated read only SQLite authorizer covered by command verification and `test_readonly_authorizer_blocks_writes`
- AC-4: Structured query tool error recovery and collapsible diagnostics covered by UI steps and `test_tool_error_structured_recovery`
- AC-5: Informative empty dataset guidance covered by UI steps and `test_empty_dataset_remedial_guidance`
- AC-6: Transparent quick actions chat logging covered by UI steps and `test_quick_action_user_message_logging`
- AC-7: Tool parameter sanitization and bounds checking covered by `test_tool_parameter_sanitization`
