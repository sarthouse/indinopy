from django.urls import path
from . import views

app_name = "mes"

urlpatterns = [
    # ── Gobernanza: Registro de e-OPs ──────────────────────────────────
    path("eops/", views.RegistroEOPListView.as_view(), name="eop_list"),
    path("eops/<uuid:uuid>/", views.RegistroEOPDetailView.as_view(), name="eop_detail"),
    path("eops/<uuid:uuid>/aprobar/", views.AprobarEOPActionView.as_view(), name="eop_aprobar"),
    path("eops/<uuid:uuid>/vetar/", views.VetarEOPActionView.as_view(), name="eop_vetar"),

    # ── Gobernanza: Tribunal y Alertas ─────────────────────────────────
    path("alertas/", views.AlertaColusionListView.as_view(), name="alerta_list"),
    path("tribunal/", views.TribunalArbitrajeListView.as_view(), name="tribunal_list"),
    path("tribunal/<int:pk>/", views.TribunalArbitrajeDetailView.as_view(), name="tribunal_detail"),

    # ── Gestión de PTFs (por la Comisión) ──────────────────────────────
    path("ptf/", views.PTFListView.as_view(), name="ptf_list"),
    path("ptf/<int:pk>/", views.PTFDetailView.as_view(), name="ptf_detail"),
    path("ptf/<int:pk>/revocar/", views.RevocarPTFActionView.as_view(), name="ptf_revocar"),

    # ── Portal del PTF (uso personal en campo) ─────────────────────────
    path("ptf/portal/", views.PTFPortalView.as_view(), name="ptf_portal"),
    path("ptf/registrar-clave/", views.RegistrarClavePublicaActionView.as_view(), name="ptf_registrar_clave"),
]
