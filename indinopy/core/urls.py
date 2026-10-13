"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings

from apps.contactos.views import LoginPortalView, LogoutPortalView, RegistroTalleristaView
from core.views import HomeIndexView

urlpatterns = [
    # Inicio / Dashboard de Despacho
    path('', HomeIndexView.as_view(), name='home'),

    # Autenticación y Registro Portal
    path('login/', LoginPortalView.as_view(), name='login'),
    path('logout/', LogoutPortalView.as_view(), name='logout'),
    path('registro/', RegistroTalleristaView.as_view(), name='registro'),

    path('admin/', admin.site.urls),
    path('contactos/', include('apps.contactos.urls', namespace='contactos')),
    path('documentos/', include('apps.documentos.urls', namespace='documentos')),
    path('produccion/', include('apps.produccion.urls', namespace='produccion')),
    path('eop/', include('apps.eop.urls', namespace='eop')),
    path('tesoreria/', include('apps.tesoreria.urls', namespace='tesoreria')),
    path('inventario/', include('apps.inventario.urls', namespace='inventario')),
    path('compras/', include('apps.compras.urls', namespace='compras')),
    path('contabilidad/', include('apps.contabilidad.urls', namespace='contabilidad')),
    path('ventas/', include('apps.ventas.urls', namespace='ventas')),
    path('nomina/', include('apps.nomina.urls', namespace='nomina')),
    path('comunicaciones/', include('apps.comunicaciones.urls', namespace='comunicaciones')),
    path('integraciones/woocommerce/', include('apps.integraciones.woocommerce.urls', namespace='integraciones_woocommerce')),
]
