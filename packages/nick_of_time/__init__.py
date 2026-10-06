"""Nick of Time shared package (spec 01 §6.1, FR-01).

Holds the contract models, identifiers and, as their specs land, the policy engine, the store and the receipt builder.
Every Python app imports it; nobody re-declares a contract model. `packages/` must be on the import path (pytest.ini
does it for tests; the apps set PYTHONPATH).
"""

CONTRACT_VERSION = "1.8.0"   # spec 01 contract version, reported by /api/health
