# Differentiators versus other teams (for the final README and the video)

With ~180 teams and 10 days, most will converge on a chat with RAG over made-up policies, almost always W1, with the LLM deciding, containment metrics on a demo and no held-out. What sets us apart, each item tied to a challenge criterion and with a proof we show:

| Differentiator | Challenge criterion | How it is shown |
| --- | --- | --- |
| Visible verification: accepted ≠ verified; tool down → unconfirmed action | Point 2 | `tool_failure` case in the video |
| Policy outside the model, with every DENY as a row and guardrails with IDs | Points 3 and 5 | The injection fools the text, not the rule |
| Configurable approval mode and closing always by a human | "AI should not be autonomous just because it can" | Supervised switch in the console |
| Evaluation by final state, pass^4, n per cell, ES/PT and attacks, on a sealed held-out | Points 4 and 5 | Table with failures included |
| Agent blocks measured against the dataset's real `is_fraud` | Unsafe outcomes | A metric we did not write |
| The 15 numbers reproducible with `make setup` in 60 s and corrected in public | Point 1, Data Analytics | Number → query → CSV index in `docs/eda/README.md` |
| Regulatory clock per country with source | Business reasoning | Business day 2 visible in the case |
| Two actors with separate tools and customer notification at every status | Escalation quality | Console + customer panel |
| Data / external / assumption / simulated / projected labels everywhere | The honesty the kickoff asks for | Every number in the pitch and the README |

Where we could lose: if the end-to-end case does not run by Wednesday 30; if the ES/PT classifier ends up weak and the learned component looks like decoration (the rules baseline comes before the model); and if the demo looks poor next to pretty interfaces (`/chat` starts from `agent-chat-ui`).
