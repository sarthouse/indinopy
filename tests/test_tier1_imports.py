"""
Tier 1 Imports & Circular Dependency AST Verification Tests.

Verifies:
- Zero inline imports across all Python source modules in apps/, core/, tests/,
  and root, EXCEPT the 5 permissible Django lifecycle exceptions:
    1. manage.py:main
    2. apps/tesoreria/apps.py:ready
    3. apps/compras/apps.py:ready
    4. apps/inventario/apps.py:ready
    5. apps/produccion/apps.py:ready
- Circular dependency decoupling:
    - apps.produccion.models does not import apps.federacion
    - ContabilizacionDocumentoService is hoisted in apps.contabilidad.servicios_afip
"""

import ast
import os
from django.conf import settings
from django.test import SimpleTestCase


class ASTZeroInlineImportsTests(SimpleTestCase):
    """
    AST inspection ensuring all stdlib, framework, same-app, and inter-app
    inline imports have been hoisted to module level.
    """

    PERMISSIBLE_EXCEPTIONS = {
        ("manage.py", "main"),
        ("apps/tesoreria/apps.py", "ready"),
        ("apps/compras/apps.py", "ready"),
        ("apps/inventario/apps.py", "ready"),
        ("apps/produccion/apps.py", "ready"),
    }

    def _get_python_files(self):
        """Yield relative paths of all relevant Python files in the workspace."""
        base_dir = str(settings.BASE_DIR)
        scan_dirs = ["apps", "core", "tests"]
        single_files = ["manage.py"]

        for single in single_files:
            full = os.path.join(base_dir, single)
            if os.path.isfile(full):
                yield single, full

        for sdir in scan_dirs:
            abs_dir = os.path.join(base_dir, sdir)
            if not os.path.isdir(abs_dir):
                continue
            for root, dirs, files in os.walk(abs_dir):
                # Skip cache and virtualenv directories
                dirs[:] = [d for d in dirs if d not in ("__pycache__", ".venv", ".git", ".agents")]
                for f in files:
                    if f.endswith(".py"):
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, base_dir)
                        yield rel_path, full_path

    def test_zero_unauthorized_inline_imports(self):
        """
        Verify that no unauthorized inline imports exist inside functions or methods.
        Only the 5 permissible lifecycle exceptions are allowed.
        """
        violations = []

        for rel_path, full_path in self._get_python_files():
            normalized_rel = rel_path.replace("\\", "/")
            try:
                with open(full_path, "r", encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=normalized_rel)
            except Exception as exc:
                violations.append((normalized_rel, 0, f"Parse error: {exc}"))
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fn_name = node.name
                    if (normalized_rel, fn_name) in self.PERMISSIBLE_EXCEPTIONS:
                        continue

                    # Search for any ast.Import or ast.ImportFrom directly or nested inside this function
                    for child in ast.walk(node):
                        if child is node:
                            continue
                        if isinstance(child, (ast.Import, ast.ImportFrom)):
                            imported_names = []
                            if isinstance(child, ast.Import):
                                imported_names = [alias.name for alias in child.names]
                            elif isinstance(child, ast.ImportFrom):
                                mod = child.module or ""
                                imported_names = [f"{mod}.{alias.name}" for alias in child.names]

                            violations.append(
                                (
                                    normalized_rel,
                                    child.lineno,
                                    fn_name,
                                    ", ".join(imported_names),
                                )
                            )

        self.assertEqual(
            len(violations),
            0,
            f"Found {len(violations)} unauthorized inline import(s):\n"
            + "\n".join(
                f"  - {file}:{line} in function '{fn}': importing {names}"
                for file, line, fn, names in violations
            ),
        )

    def test_permissible_lifecycle_exceptions_exist(self):
        """Verify each of the 5 permissible lifecycle exceptions exists in the codebase."""
        base_dir = str(settings.BASE_DIR)
        for rel_path, fn_name in self.PERMISSIBLE_EXCEPTIONS:
            full_path = os.path.join(base_dir, rel_path)
            self.assertTrue(
                os.path.isfile(full_path),
                f"Expected permissible exception file not found: {rel_path}",
            )
            with open(full_path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=rel_path)

            found_fn = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == fn_name
                for node in ast.walk(tree)
            )
            self.assertTrue(
                found_fn,
                f"Expected function '{fn_name}' in '{rel_path}' not found.",
            )


class CircularDependencyDecouplingTests(SimpleTestCase):
    """
    Verifies that circular dependencies have been cleanly decoupled:
    1. apps.produccion.models does not import apps.federacion.
    2. apps.contabilidad.servicios_afip has ContabilizacionDocumentoService hoisted at module level.
    """

    def test_produccion_models_has_no_federacion_import(self):
        """apps/produccion/models.py must NOT import apps.federacion in AST."""
        base_dir = str(settings.BASE_DIR)
        prod_models_path = os.path.join(base_dir, "apps", "produccion", "models.py")
        with open(prod_models_path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename="apps/produccion/models.py")

        federacion_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "federacion" in alias.name:
                        federacion_imports.append((node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module and "federacion" in node.module:
                    federacion_imports.append((node.lineno, node.module))

        self.assertEqual(
            federacion_imports,
            [],
            f"apps/produccion/models.py must NOT import apps.federacion: {federacion_imports}",
        )

    def test_contabilidad_servicios_afip_hoisted_contabilizacion_service(self):
        """
        apps/contabilidad/servicios_afip.py must import ContabilizacionDocumentoService
        at module level (top-level), not inside any function.
        """
        base_dir = str(settings.BASE_DIR)
        afip_path = os.path.join(base_dir, "apps", "contabilidad", "servicios_afip.py")
        with open(afip_path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename="apps/contabilidad/servicios_afip.py")

        top_level_import_found = False
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                names = [a.name for a in node.names]
                if "ContabilizacionDocumentoService" in names:
                    top_level_import_found = True
                    break

        self.assertTrue(
            top_level_import_found,
            "ContabilizacionDocumentoService must be imported at top level in apps/contabilidad/servicios_afip.py",
        )
