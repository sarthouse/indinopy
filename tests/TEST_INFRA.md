# E2E Test Infra: ERP Indinopy

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on internal private implementation details.
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial + Real-World Workload Testing.
- Strict NO-DB-CHANGES: All tests must run cleanly against the existing schema; verify zero schema alterations via dry-run migrations.

## Feature Inventory & Test Mapping
| # | Feature | Requirement Source | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Cross-Feature) | Tier 4 (Real-World) |
|---|---|---|---|---|---|---|
| F1 | System Check & Baseline Health | ORIGINAL_REQUEST §Acceptance Criteria | 5 | 5 | ✓ | ✓ |
| F2 | Celery & Redis Configuration | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ | ✓ |
| F3 | Import Hoisting & Zero Inline Imports | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| F4 | Circular Dependency Resolution | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| F5 | Nomenclature & Model Immutability | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| F6 | ORM Optimization & N+1 Prevention | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| F7 | View & Admin Query Efficiency | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| F8 | Communication Payloads Alignment | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Test Runner: Python `unittest` / Django test runner (`python manage.py test tests`).
- Test Layout:
  - `tests/`:
    - `test_tier1_baseline.py`: Django system checks (`manage.py check`), `makemigrations --dry-run` zero changes, syntax compilation, Celery app initialization, Redis URL parsing.
    - `test_tier1_imports.py`: AST-based verification of 0 inline imports in function bodies across all apps (allowing only lifecycle `AppConfig.ready` and `manage.py`).
    - `test_tier2_boundaries.py`: Choice max_length compliance (LiquidacionNomina 'REV_TESORERIA'), edge case payload validation, empty payloads, invalid types.
    - `test_tier3_cross_feature.py`: Produccion-Federacion interaction, e-OP creation, mirror OP reception, escrow release.
    - `test_tier4_workloads.py`: Full simulated flow from sales order to manufacturing part reception and accounting journal entry generation.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|---|---|---|
| 1 | Decentralized e-OP Lifecycle | F1, F4, F5, F8 | High |
| 2 | High-Volume Payroll LSD Export | F1, F5, F6 | Medium |
| 3 | Manufacturing Supply Scheduler Run | F1, F6 | Medium |
| 4 | Accounting Invoice Journal Entry Generation | F1, F4, F6 | High |
| 5 | Celery Async Task Dispatch | F2 | Medium |
