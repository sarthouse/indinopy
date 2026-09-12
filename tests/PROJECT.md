# Project: ERP Indinopy Audit & Architectural Refactoring

## Architecture
ERP Indinopy is a modular Django ERP system with decentralized federation and MES capabilities.
- **Core / Infrastructure**: `core` (settings, urls, wsgi, asgi, celery), `apps.base`, `apps.documentos`, `apps.contactos`
- **ERP Business Modules**:
  - `apps.inventario`: Warehouses, products, quants, stock movements, replenishment scheduler.
  - `apps.compras`: Supplier management, purchase orders, reception.
  - `apps.ventas`: Customers, sales orders, WooCommerce integration webhooks.
  - `apps.produccion`: Production orders (OP), recipes (Receta), bill of materials (BOM), stage tracking.
  - `apps.tesoreria`: Payment orders, collections, escrow contracts, UCI currency index.
  - `apps.contabilidad`: General ledger, accounts, journal entries, AFIP WSFE electronic billing.
  - `apps.nomina`: Employees, payroll runs (LiquidacionNomina), AFIP Libro de Sueldos Digital (LSD).
- **Decentralized / Manufacturing Nodes**:
  - `apps.federacion`: Federated workshop network, electronic production orders (e-OP), mirror OPs, node registry.
  - `apps.mes`: Manufacturing Execution System, real-time stage execution, PTF Ed25519 digital signatures, arbitration tribunal.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| F1 | Baseline System Check Remediation | Fix `admin.E108` (`tallerista_principal`), fix `fields.E009` (`LiquidacionNomina.estado` choice `'REV_TESORERIA'`), default `NODE_ROLE=DEV`, wire `federacion.urls`. | M1 | ORIGINAL_REQUEST §Acceptance Criteria & Survey 1 |
| F2 | Celery & Redis Infrastructure | Create `core/celery.py`, export `celery_app` in `core/__init__.py`, configure environment-driven Redis broker/backend in `settings.py`. | M1 | ORIGINAL_REQUEST §R5 & Survey 1 |
| F3 | Import Refactoring & Hoisting | Hoist 41 stdlib/framework inline imports and 14 same-app imports to module level; leave only 5 Django lifecycle exceptions. | M2 | ORIGINAL_REQUEST §R3 & Survey 3 |
| F4 | Circular Dependency Decoupling | Decouple `OrdenProduccion.clean()` from `FederacionCreditoService` via service layer; decouple AFIP and accounting. | M2 | ORIGINAL_REQUEST §R3 & Survey 3 |
| F5 | Nomenclature & Attribute Alignment | Align `Contacto` queries (`cuil`), `Receta` lookups (`producto_template`), remove `tallerista_principal` references under strict NO-DB-CHANGES. | M2 | ORIGINAL_REQUEST §R1 & Survey 2/3 |
| F6 | ORM N+1 Optimization in Services | Add `select_related`/`prefetch_related` in `exportar_lsd_csv`, `liquidar_mes`, `contabilizar_factura`, `calcular_insumos`, `scheduler`. | M3 | ORIGINAL_REQUEST §R2 & Survey 2 |
| F7 | ORM Optimization in Views & Admin | Optimize 18 primary Class-Based Views and 39 `ModelAdmin` classes (`list_select_related`). | M3 | ORIGINAL_REQUEST §R2 & Survey 2 |
| F8 | Communication Payloads Alignment | Reconcile JSON payload keys (`comitente_cuit`/`cuit_comitente`), Escrow release UUID/int lookup, Ed25519 signature payload hashing. | M4 | ORIGINAL_REQUEST §R4 & Survey 3 |
| F9 | Comprehensive E2E Testing Suite | Build opaque-box test suite across Tiers 1-4 verifying checks, migrations, syntax, Celery, and payload workflows. | M5 | ORIGINAL_REQUEST §Acceptance Criteria & Dual Track |
| F10 | Forensic Integrity Verification | Forensic audit validating genuine implementation, zero cheating/hardcoding, and full compliance. | M5 | Dual Track & Forensic Audit Policy |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | Baseline Health & Celery/Redis Infra | F1, F2: Fix check blockers, create celery.py, configure Redis settings. | none | DONE |
| M2 | Imports & Nomenclature Refactoring | F3, F4, F5: Eliminate inline imports, decouple circular dependencies, align attributes with strict NO-DB-CHANGES. | M1 | PLANNED |
| M3 | ORM Query & N+1 Optimization | F6, F7: Optimize services, batch operations, Class-Based Views, ModelAdmin. | M2 | PLANNED |
| M4 | Communication Payloads Alignment | F8: Reconcile JSON schemas and cryptographic verification between produccion, federacion, mes. | M2 | PLANNED |
| M5 | E2E Testing & Forensic Integrity Gate | F9, F10: Comprehensive automated test suite, adversarial tests, forensic audit. | M3, M4 | PLANNED |

## Interface Contracts
### `apps.produccion` ↔ `apps.federacion`
- `ProduccionService.confirmar_op(op)` initiates federation sync only when `op.es_eop_federada` is True.
- Quota check `consultar_cupo_mes(cuit)` is performed at service level, not in `Model.clean()`.
- Payload sent to `/api/v1/eop/espejo/` must include: `comitente_cuit`, `cuit_comitente` (supported interchangeably), `numero_op_origen`, `cantidad_total`, `etapas`, `payload_canonico`.

### `apps.federacion` ↔ `apps.mes`
- Workshop resolution and stage progress webhook `/api/v1/eop/parte-produccion/`: payload contains `uuid_eop`, `lineas`, `hash_etapa`, `firma_digital`.
- Digital signatures (Ed25519) must follow canonical JSON UTF-8 payload representation.

### `apps.federacion` ↔ `apps.tesoreria`
- `EscrowService.liberar_hito(hito_id, firma_ptf=None)` accepts either `id` (int) or `uuid` (UUID/str) lookup to support both local admin and asynchronous task callers.

## Code Layout
- `core/`: Global Django settings, URL routing, WSGI/ASGI, `celery.py`.
- `apps/<app_name>/`:
  - `models.py`: Database models (STRICTLY IMMUTABLE).
  - `services.py`: Domain business logic and batch query optimizations.
  - `views.py`: Web and API views.
  - `serializers.py`: DRF serialization and validation.
  - `tasks.py`: Asynchronous Celery tasks (`@shared_task`).
  - `admin.py`: Django admin registrations.
  - `urls.py`: App routing.
- `tests/`: Automated unit, integration, and E2E test suites.

## Hard Constraints
- Strict NO-DB-CHANGES: No alterations to Model names, field names, or database column types. `makemigrations --dry-run` must always yield "No changes detected".
- No inline imports inside function bodies (except standard Django lifecycle `AppConfig.ready()` and `manage.py:main`).
- Zero issues on `python manage.py check`.
