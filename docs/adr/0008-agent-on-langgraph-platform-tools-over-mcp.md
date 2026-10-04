# 0008. Agent on LangGraph Platform, customer tools as an MCP server

- **Status:** Accepted
- **Date:** 2026-09-28 (reconfirmed 2026-10-03)
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** specs 01, 03, 04, [`docs/assets/architecture_option_a.svg`](../assets/architecture_option_a.svg)

## Context
The agent needs a typed state, human-in-the-loop interrupts, a checkpointer, traces and a deployment that does not
compete with the web stack for time. The LangSmith organization is on the Plus tier (cloud deployments available).

## Decision
The LangGraph graph (`dispute_intake`: understand → identity → retrieve → decide → act → verify → receipt + handoff)
runs on **LangGraph Platform**, deployed from GitHub with `langgraph.json`, with a managed checkpointer and traces.
The seven customer tools run as a **FastMCP server** on the EC2 at `mcp.nickoftime.salazarvalverdeai.com`, behind an
API key; they enforce the session's `customer_id` and the policies themselves. The browser never calls Platform: the
backend proxies runs and injects the session server-side.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| A: Platform + MCP on EC2 (chosen) | Managed graph runtime, Studio, traces, simple deploy; tools reusable by any MCP client | Tools exposed over the internet (API key + allowlist); two deploy targets |
| B: graph inside FastAPI on the EC2 | One deploy, one log | We run the graph runtime and checkpointer ourselves |
| Bedrock Agents / AgentCore | AWS-native | Policies move into the vendor runtime; less control over verification |

## Consequences
Option B stays documented as the fallback (same graph, the tool adapter changes from MCP to direct import). The MCP
server needs public HTTPS before the deployed graph can be tested; locally, `langgraph dev` plus a local MCP server.

## Confidence
Medium-high. Revisit if Platform latency or limits break the demo; fall back to option B.
