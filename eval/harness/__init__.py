"""Evaluation harness (spec 10): runs a case set on one or more arms and compares the final state, never the text.

    python -m eval.harness run --set dev --arms S0,S1 --api http://localhost:8000
    from eval.harness import run_set          # spec 15 calls it for benchmark B2 (FR-06)
"""
from eval.harness.client import Api, HarnessError
from eval.harness.run import run_one, run_set, write_outputs

__all__ = ["Api", "HarnessError", "run_one", "run_set", "write_outputs"]
