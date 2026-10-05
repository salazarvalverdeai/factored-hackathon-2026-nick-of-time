"""The real stack for `make eval`, on one machine (spec 10 T6): the store-backed api with the evaluation hooks, the real
MCP server and the real `dispute_intake` graph under `langgraph dev`, over one in-memory store and gold read-only.

Local only: nothing in apps/ imports this package, so no deployed image carries the hooks (spec 01 FR-05).
"""
