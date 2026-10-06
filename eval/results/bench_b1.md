[simulated] pre-registered test run; test split decided by fixed rules, without independent human review (test_review: rules-v1, ADR 0028)

| Arm | Status | Accuracy [95% CI] | Macro-F1 es / pt | Dispute recall | Person recall | Slot acc. | No tool call | Errors | p50 / p95 ms | USD per 1k | Bar | Pareto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sonnet-4-6 | ok | 0.9788 [0.9514, 0.9909] | 0.9659 / 0.9913 | 0.9787 | 0.9574 | 0.9757 | 0 | 0 | 1130 / 1369 | 5.14642 | no | yes |
| mistral-large-3 | ok | 0.9746 [0.9457, 0.9883] | 0.9657 / 0.9826 | 1.0 | 0.9574 | 0.9126 | 0 | 0 | 614 / 1368 | 0.311097 | no | yes |
| deepseek-v3-2 | ok | 0.9661 [0.9345, 0.9827] | 0.9496 / 0.9826 | 0.9894 | 0.9574 | 0.8058 | 0 | 0 | 3398 / 9684 | 0.691094 | no | no |
| nova-2-lite | ok | 0.9576 [0.9238, 0.9768] | 0.9575 / 0.9568 | 0.9787 | 0.9362 | 0.7816 | 0 | 0 | 748 / 1276 | 0.62234 | no | no |
| qwen3-235b | ok | 0.9492 [0.9132, 0.9707] | 0.9225 / 0.9736 | 0.9468 | 0.9574 | 0.8689 | 0 | 0 | 903 / 1415 | 0.167243 | no | yes |
| gpt-oss-120b | ok | 0.9237 [0.8827, 0.9512] | 0.9355 / 0.9362 | 0.9149 | 0.9574 | 0.8447 | 7 | 0 | 1309 / 2936 | 0.195015 | no | no |
| haiku-4-5 | ok | 0.9237 [0.8827, 0.9512] | 0.9322 / 0.9147 | 0.9894 | 0.9149 | 0.7718 | 0 | 0 | 1093 / 1631 | 1.837937 | no | no |
| b1_tfidf_lr | ok | 0.9153 [0.8727, 0.9445] | 0.916 / 0.9136 | 0.9574 | 0.8936 | 0.8398 | 0 | 0 | 1.037 / 1.412 | 0.0 | no | yes |
| gpt-oss-20b | ok | 0.9153 [0.8727, 0.9445] | 0.9205 / 0.9351 | 0.8511 | 0.9574 | 0.7282 | 8 | 0 | 741 / 1409 | 0.097236 | no | no |
| nova-pro | ok | 0.9068 [0.8629, 0.9376] | 0.8996 / 0.9147 | 0.9468 | 0.9149 | 0.8301 | 0 | 0 | 839 / 1147 | 0.819932 | no | no |
| qwen3-32b | ok | 0.8686 [0.8196, 0.9059] | 0.864 / 0.8657 | 0.9787 | 0.9149 | 0.767 | 0 | 0 | 451 / 662 | 0.114431 | no | no |
| llama-4-scout | ok | 0.8602 [0.8101, 0.8987] | 0.8368 / 0.8609 | 0.9894 | 0.9574 | 0.7816 | 0 | 0 | 495 / 620 | 0.136384 | no | no |
| nova-micro | ok | 0.8347 [0.7821, 0.8767] | 0.8168 / 0.8571 | 0.9787 | 0.8085 | 0.699 | 0 | 0 | 549 / 690 | 0.035351 | no | no |
| ministral-3-14b | ok | 0.7754 [0.718, 0.824] | 0.7595 / 0.7694 | 0.9574 | 0.9574 | 0.7816 | 1 | 0 | 395 / 580 | 0.101027 | no | no |
| nova-lite | ok | 0.7585 [0.7, 0.8087] | 0.7155 / 0.7904 | 0.8936 | 0.9574 | 0.7136 | 0 | 1 (ProviderUnavailable 1) | 815 / 1211 | 0.060699 | no | no |
| ministral-3-8b | ok | 0.7415 [0.6821, 0.7932] | 0.6745 / 0.8221 | 0.8191 | 0.9574 | 0.7621 | 1 | 0 | 338 / 478 | 0.075835 | no | no |
| llama-4-maverick | ok | 0.6992 [0.6378, 0.7541] | 0.6623 / 0.73 | 0.617 | 0.9787 | 0.767 | 0 | 0 | 504 / 607 | 0.203497 | no | no |
| b0_rules | ok | 0.6144 [0.5509, 0.6742] | 0.5828 / 0.6683 | 0.5 | 0.6383 | 0.8398 | 0 | 0 | 0.154 / 0.31 | 0.0 | no | no |
| gemma-3-12b | no structured output: no tool call returned; toolChoice=tool; stopReason=end_turn; reply='```json\n{\n | | | | | | | | | | | |
| gemma-3-27b | no structured output: no tool call returned; toolChoice=tool; stopReason=end_turn; reply='```json\n{\n | | | | | | | | | | | |
| llama-3-3-70b | no structured output: no tool call returned; toolChoice=auto; stopReason=end_turn; reply='{"type": "fu | | | | | | | | | | | |
| nemotron-nano-3 | no structured output: no tool call returned; toolChoice=tool; stopReason=end_turn; reply='{\n  "messag | | | | | | | | | | | |
| sonnet-5-5 | unavailable: AccessDeniedException: anthropic.claude-sonnet-5-5 is not available for this acc | | | | | | | | | | | |
| jev | unavailable: TYPESAFE_API_KEY is not in the environment | | | | | | | | | | | |

## Model map (`understand`, PROTOCOL §2.3)

- Best measured: `sonnet-4-6`
- Best arm for the bar (rule 2): `None`
- Cheapest that meets the bar: `None`
- Chosen: `b0_rules` ([assumption] D-077 pending: fallback not in PROTOCOL §2.3 (every measured arm fails rule 1 (hard limits)): the no-LLM option B0 stays)
- Reading: [assumption] D-077 pending: the best arm of rule 2 is chosen among the arms that pass rule 1 (spec 11 §4, among the rest)
- Note: chosen by [assumption] D-077 pending: fallback not in PROTOCOL §2.3 (every measured arm fails rule 1 (hard limits)): the no-LLM option B0 stays
