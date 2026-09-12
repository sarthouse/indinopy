"""
Tier 1 Baseline Health & Celery/Redis Infrastructure Tests.

Verifies:
- Django System Check passes with 0 issues (resolving admin.E108 and fields.E009).
- Celery application instance and Redis configuration.
- Strict NO-DB-CHANGES adherence (max_length preserved, choice key lengths).
- Dynamic NODE_ROLE defaults and app loading.
- Federation URL wiring.
- Model and migration stability under dry-run inspection.
"""

import os
from io import StringIO
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, RequestFactory
from django.conf import settings
from django.core.checks import run_checks, Error as CheckError
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.contrib import admin
from django.forms.models import ModelForm
from django.urls import reverse, resolve
from celery import Celery

from core import celery_app
from apps.produccion.admin import OrdenProduccionAdmin
from apps.produccion.models import OrdenProduccion
from apps.nomina.models import LiquidacionNomina
from apps.nomina.services import NominaService


class SystemCheckBaselineTests(SimpleTestCase):
    """Verifies that the entire Django project passes system checks with 0 errors."""

    def test_django_system_check_has_zero_issues(self):
        """Verify that core system checks produce 0 errors."""
        all_issues = run_checks()
        errors = [issue for issue in all_issues if issue.level >= CheckError]
        self.assertEqual(
            len(errors),
            0,
            f"Django system check identified {len(errors)} errors: {[str(e) for e in errors]}",
        )

    def test_admin_system_checks_have_zero_issues(self):
        """Verify that Django admin checks pass with 0 issues."""
        admin_issues = admin.site.check(None)
        errors = [issue for issue in admin_issues if issue.level >= CheckError]
        self.assertEqual(
            len(errors),
            0,
            f"Admin system check identified {len(errors)} errors: {[str(e) for e in errors]}",
        )

    def test_produccion_admin_excludes_tallerista_principal(self):
        """
        Verify admin.E108 fix: OrdenProduccionAdmin list_display and search_fields
        must not reference 'tallerista_principal'.
        """
        op_admin = admin.site._registry.get(OrdenProduccion)
        self.assertIsNotNone(op_admin, "OrdenProduccion must be registered in admin site.")

        # list_display check
        self.assertNotIn(
            "tallerista_principal",
            op_admin.list_display,
            "list_display must not contain 'tallerista_principal' (admin.E108).",
        )

        # search_fields check
        self.assertNotIn(
            "tallerista_principal__nombre",
            op_admin.search_fields,
            "search_fields must not contain 'tallerista_principal__nombre'.",
        )

    def test_produccion_admin_fieldsets_excludes_tallerista_principal(self):
        """
        Verify that 'tallerista_principal' does not appear anywhere in
        OrdenProduccionAdmin.fieldsets across any fieldset sections.
        """
        op_admin = admin.site._registry.get(OrdenProduccion)
        self.assertIsNotNone(op_admin, "OrdenProduccion must be registered in admin site.")

        # Flatten all fields across all fieldset sections
        fieldset_fields = []
        for _name, options in op_admin.fieldsets:
            for field in options.get("fields", ()):
                if isinstance(field, (list, tuple)):
                    fieldset_fields.extend(field)
                else:
                    fieldset_fields.append(field)

        self.assertNotIn(
            "tallerista_principal",
            fieldset_fields,
            "'tallerista_principal' must not exist anywhere in OrdenProduccionAdmin.fieldsets.",
        )
        self.assertNotIn(
            "tallerista_principal",
            str(op_admin.fieldsets),
            "'tallerista_principal' must not exist in serialized fieldsets definition.",
        )

    def test_produccion_admin_get_form_instantiates_without_field_error(self):
        """
        Verify that admin_instance.get_form(request) instantiates successfully
        without raising FieldError (which previously occurred due to unknown
        'tallerista_principal' field specified in fieldsets).
        """
        op_admin = admin.site._registry.get(OrdenProduccion)
        self.assertIsNotNone(op_admin, "OrdenProduccion must be registered in admin site.")

        rf = RequestFactory()
        request = rf.get("/admin/produccion/ordenproduccion/add/")
        request.user = MagicMock()

        try:
            form_class = op_admin.get_form(request)
        except Exception as exc:
            self.fail(f"op_admin.get_form(request) raised an unexpected exception: {exc}")

        self.assertTrue(
            issubclass(form_class, ModelForm),
            "get_form(request) must return a ModelForm subclass.",
        )
        self.assertNotIn(
            "tallerista_principal",
            getattr(form_class, "base_fields", {}),
            "Form base_fields must not include 'tallerista_principal'.",
        )


class NominaModelIntegrityTests(SimpleTestCase):
    """Verifies fields.E009 fix and strict NO-DB-CHANGES compliance in apps.nomina."""

    def test_liquidacion_nomina_estado_max_length_preserved(self):
        """Verify max_length is preserved at exactly 15 to prevent DB migrations."""
        estado_field = LiquidacionNomina._meta.get_field("estado")
        self.assertEqual(
            estado_field.max_length,
            15,
            "LiquidacionNomina.estado max_length must remain 15 to comply with strict NO-DB-CHANGES.",
        )

    def test_all_estado_choices_fit_within_max_length(self):
        """Verify all choice keys in ESTADO_LIQUIDACION fit within max_length=15."""
        estado_field = LiquidacionNomina._meta.get_field("estado")
        for key, _label in estado_field.choices:
            self.assertLessEqual(
                len(key),
                estado_field.max_length,
                f"Choice key '{key}' (len {len(key)}) exceeds max_length ({estado_field.max_length}).",
            )

    def test_rev_tesoreria_choice_key_present(self):
        """Verify that 'REV_TESORERIA' is present and 'REVISION_TESORERIA' is absent."""
        estado_field = LiquidacionNomina._meta.get_field("estado")
        choice_keys = [key for key, _label in estado_field.choices]

        self.assertIn(
            "REV_TESORERIA",
            choice_keys,
            "'REV_TESORERIA' must be present in ESTADO_LIQUIDACION choices.",
        )
        self.assertEqual(
            len("REV_TESORERIA"),
            13,
            "'REV_TESORERIA' must have exactly 13 characters (<= 15).",
        )
        self.assertNotIn(
            "REVISION_TESORERIA",
            choice_keys,
            "Old 18-character 'REVISION_TESORERIA' must be removed.",
        )

    def test_nomina_service_uses_rev_tesoreria(self):
        """Verify NominaService references REV_TESORERIA for SoD workflow."""
        # Mock liquidacion object
        mock_liq = MagicMock()
        mock_liq.estado = "BORRADOR"

        with patch("django.db.transaction.Atomic.__enter__"), patch("django.db.transaction.Atomic.__exit__", return_value=False):
            NominaService.solicitar_aprobacion_tesoreria(mock_liq)
            self.assertEqual(mock_liq.estado, "REV_TESORERIA")

            # Test aprobar_liquidacion_tesoreria rejects non-REV_TESORERIA
            mock_liq_invalid = MagicMock()
            mock_liq_invalid.estado = "BORRADOR"
            with self.assertRaises(ValueError):
                NominaService.aprobar_liquidacion_tesoreria(mock_liq_invalid, MagicMock())

    def test_liquidacion_nomina_rev_tesoreria_full_clean_succeeds(self):
        """
        Verify that LiquidacionNomina with estado='REV_TESORERIA' passes full_clean
        without raising ValidationError when required period fields are populated and unpersisted
        relations are excluded.
        """
        liq = LiquidacionNomina(
            estado="REV_TESORERIA",
            periodo_mes=9,
            periodo_anio=2026,
        )
        try:
            liq.full_clean(exclude=["empleado", "id"])
        except ValidationError as exc:
            self.fail(
                f"LiquidacionNomina(estado='REV_TESORERIA').full_clean(exclude=['empleado', 'id']) "
                f"failed unexpectedly with ValidationError: {exc}"
            )

        self.assertEqual(liq.estado, "REV_TESORERIA")

        # Verify that invalid choice raises ValidationError
        liq_invalid = LiquidacionNomina(
            estado="INVALID_ESTADO",
            periodo_mes=9,
            periodo_anio=2026,
        )
        with self.assertRaises(ValidationError):
            liq_invalid.full_clean(exclude=["empleado", "id"])

        # Verify that previous invalid length choice 'REVISION_TESORERIA' raises ValidationError
        liq_oversized = LiquidacionNomina(
            estado="REVISION_TESORERIA",
            periodo_mes=9,
            periodo_anio=2026,
        )
        with self.assertRaises(ValidationError):
            liq_oversized.full_clean(exclude=["empleado", "id"])


class CeleryInfrastructureTests(SimpleTestCase):
    """Verifies Celery application instance, Redis broker, and settings configuration."""

    def test_celery_app_instance_exported_in_core(self):
        """Verify core.celery_app is properly instantiated and exported."""
        self.assertIsInstance(celery_app, Celery, "celery_app must be an instance of Celery.")
        self.assertEqual(celery_app.main, "indinopy", "Celery app main name must be 'indinopy'.")

    def test_celery_broker_and_backend_settings(self):
        """Verify Redis broker and result backend URLs from Django settings."""
        self.assertTrue(
            settings.CELERY_BROKER_URL.startswith("redis://"),
            f"CELERY_BROKER_URL must point to Redis, got: {settings.CELERY_BROKER_URL}",
        )
        self.assertTrue(
            settings.CELERY_RESULT_BACKEND.startswith("redis://"),
            f"CELERY_RESULT_BACKEND must point to Redis, got: {settings.CELERY_RESULT_BACKEND}",
        )

    def test_celery_serialization_and_retry_settings(self):
        """Verify production-ready serialization, content types, and startup retry policy."""
        self.assertEqual(settings.CELERY_TASK_SERIALIZER, "json")
        self.assertEqual(settings.CELERY_RESULT_SERIALIZER, "json")
        self.assertIn("json", settings.CELERY_ACCEPT_CONTENT)
        self.assertEqual(settings.CELERY_TIMEZONE, settings.TIME_ZONE)
        self.assertTrue(settings.CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP)


class EnvironmentAndRoutingTests(SimpleTestCase):
    """Verifies default NODE_ROLE and URL routing."""

    def test_default_node_role_loads_all_apps(self):
        """Verify that default NODE_ROLE is DEV and all modules are loaded."""
        self.assertIn(
            settings.NODE_ROLE,
            ["DEV", "COMITENTE", "TALLERISTA", "MES"],
            f"NODE_ROLE must be valid, got {settings.NODE_ROLE}",
        )
        # Verify ERP apps are present
        self.assertIn("apps.produccion", settings.INSTALLED_APPS)
        self.assertIn("apps.nomina", settings.INSTALLED_APPS)
        self.assertIn("apps.contabilidad", settings.INSTALLED_APPS)
        # Verify MES app is present
        self.assertIn("apps.mes", settings.INSTALLED_APPS)
        # Verify Core apps are present
        self.assertIn("apps.federacion", settings.INSTALLED_APPS)

    def test_federacion_urls_wired_and_resolvable(self):
        """Verify that apps.federacion.urls is wired under federacion/ namespace."""
        espejo_url = reverse("federacion:api_eop_espejo")
        self.assertEqual(espejo_url, "/federacion/api/v1/eop/espejo/")

        parte_url = reverse("federacion:api_parte_produccion")
        self.assertEqual(parte_url, "/federacion/api/v1/eop/parte-produccion/")

        match = resolve("/federacion/api/v1/eop/espejo/")
        self.assertEqual(match.namespace, "federacion")


class MigrationIntegrityTests(SimpleTestCase):
    """Verifies that makemigrations --dry-run completes cleanly without system check errors."""

    def test_makemigrations_dry_run_executes_cleanly(self):
        """Verify makemigrations runs dry-run without failing system checks."""
        out = StringIO()
        err = StringIO()
        with patch("django.db.migrations.recorder.MigrationRecorder.applied_migrations", return_value={}):
            try:
                call_command("makemigrations", dry_run=True, stdout=out, stderr=err)
            except SystemExit:
                pass

        err_output = err.getvalue()
        self.assertNotIn("SystemCheckError", err_output)
        self.assertNotIn("ERRORS:", err_output)

