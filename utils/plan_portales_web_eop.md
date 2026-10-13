# Plan de Implementación de Portales Web (SSR + API) - Ley e-OP

## 1. Diagnóstico del Estado Actual
- **Modelos y Servicios**: Completamente desarrollados en `apps.eop.services`, `apps.afip.services` y `apps.contabilidad`.
- **Plantillas Existentes**: Actualmente sólo existen plantillas de reportes imprimibles/PDF (`weasyprint` / HTML plano). Las vistas declaradas en `apps.eop.views` (`ContratoEOPListView`, `ContratoEOPDetailView`) y `apps.produccion.views` (`PortalTalleristaListView`) carecen de archivos `.html` base.
- **Librerías Disponibles**: Django 6.1, Django REST Framework 3.18, Alpine/HTMX vía CDN o estáticos locales.

---

## 2. Estrategia de Arquitectura: Dualidad SSR + API REST

| Ámbito | Mecanismo | Autenticación | Destinatarios | Formato Retorno |
| :--- | :--- | :--- | :--- | :--- |
| **Portal Web Tallerista** | SSR (Django Templates + HTMX) | Sesión Django / Login | Operario en taller (Celular/Desktop) | HTML responsivo (Tailwind/DaisyUI) |
| **Portal Web Comitente / Contable** | SSR (Django Templates + HTMX) | Sesión Django / Staff | Administrativo / Marca | HTML responsivo |
| **Portal Web Fiduciario** | SSR (`fimca-core`) | Sesión Django / Staff | Auditor fiduciario / FIMCA | HTML responsivo (`clearing_dashboard.html`) |
| **Sincronización Federada M2M** | API REST / Webhooks | HMAC / API Key / Token | Nodos federados / FIMCA FDI | JSON |
| **Operaciones Headless M2M** | API REST (DRF) | Token Bearer / JWT | Apps externas, ERPs satélites | JSON |

---

## 3. Plan de Acción por Fases

### Fase A: Layout Base Unificado (`indinopy/templates/base.html`)
1. Crear una plantilla base responsiva, moderna y liviana:
   - Soporte para Tailwind CSS vía CDN (o estilos encapsulados sin requerir build tool pesada de Node en backend).
   - Inclusión de **HTMX** (para interacciones asincrónicas sin recarga de página: validar CAE, confirmar borrador, simular SIPA 2%).
   - Soporte para notificaciones `messages` de Django y bloque `nav` adaptable (Tallerista vs Comitente).

### Fase B: Portal Tallerista (`apps/eop/` y `apps/produccion/`)
1. **Plantilla `produccion/portal_tallerista_list.html`**:
   - Listado de etapas/hitos asignados al tallerista autenticado.
   - Estado de pago del Escrow (Hito Cero fondeado, Hitos intermedios, Hito final en RCF).
   - Tarjeta interactiva de **PoPW**: Botón para tomar ubicación GPS (`navigator.geolocation`) y enviar el parte físico.
2. **Plantilla de Facturación Asistida y Cierre Fiscal (`eop/contrato_detail.html` / modal HTMX)**:
   - Si el hito final está retenido en RCF (`retencion_cierre_fiscal`):
     - Muestra el **Borrador de Factura C** generado por `FacturacionAsistidaService.preparar_borrador_factura_c()`:
       - Monto bruto en ARS.
       - Desglose previsional SIPA 2% (Art. 24.5).
       - Neto a cobrar.
     - **Opción 1**: Botón "Autorizar en 1-Click con ARCA" (dispara `FacturacionAsistidaService.confirmar_y_emitir_factura_asistida` vía WSFEv1).
     - **Opción 2**: Formulario "Ya facturé en el portal de ARCA": Ingreso de Pto Venta + Comprobante + CAE, validado en vivo con `constatar_factura_externa` (WSCDC).

### Fase C: Portal Comitente / Auditoría Fiscal (`apps/eop/` y `apps/contabilidad/`)
1. **Plantilla `eop/contrato_list.html` y `eop/contrato_detail.html` (Vista Marca)**:
   - Visualización del cronograma de entregas JIT y semáforo de demoras de insumos (Art. 5° bis).
   - Registro de standby devengado (0.5 SMVM diario si la marca demoró más de 5 días).
   - Panel de Crédito Fiscal Presunto del 10% (Art. 23.1 Ley e-OP) computado para el Libro IVA Digital.

### Fase D: Endpoints REST Headless para Clientes API
1. En `apps/eop/api_views.py` (o serializers DRF):
   - `GET /api/v1/eop/hitos/{id}/borrador-factura/` -> Retorna JSON con cálculo SIPA 2% y cotización UCI.
   - `POST /api/v1/eop/hitos/{id}/emitir-factura-asistida/` -> Emite CAE vía WSFEv1.
   - `POST /api/v1/eop/hitos/{id}/constatar-factura/` -> Valida comprobante externo vía WSCDC.
   - `POST /api/v1/eop/hitos/{id}/popw/` -> Registra coordenadas GPS y avance de producción.

---

## 4. Criterios de Aceptación y Validación
1. **Verificación Estática**: `python manage.py check` con 0 errores en `indinopy` y `fimca-core`.
2. **Cero Migraciones de DB**: Se aprovechan los campos existentes (`factura_asociada_arca`, `ddjj_avance_datos`, `firmas_digitales`).
3. **Usabilidad Móvil**: El tallerista puede operar desde el navegador de su teléfono sin instalar apps nativas.
