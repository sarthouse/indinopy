# Plan de Implementación de Portales Web e Interfaz (SSR + API) - Ley e-OP

**Estado del Plan:** COMPLETADO Y VERIFICADO  
**Fecha de Actualización:** Octubre de 2026  
**Entorno de Ejecución:** `indinopy` (ERP + Portal) y `fimca-core` (Nodo Central Fiduciario)

---

## 1. Diagnóstico del Estado y Objetivos Logrados

- **Modelos y Servicios de Negocio:**
  - `FacturacionAsistidaService` (`apps/afip/services.py`): Factura C para monotributo productivo, retención SIPA 2% (Art. 24.5), emisión directa con WSFEv1 y constatación de comprobantes externos con WSCDC.
  - `EOPService`, `RCFService` y `LogisticaJITService` (`apps/eop/services.py`): Control de timelocks RCF, devengamiento de intereses BADLAR (Art. 12°) y lucro cesante fabril (0.5 SMVM diario a partir del 6° día).
  - `contabilizar_credito_fiscal_presunto_eop` (`apps/contabilidad/contabilizacion.py`): Asiento de crédito presunto del 10% (Art. 23.1).
- **Frontend y Plantillas:**
  - Sistema de Server-Side Rendering (SSR) ligero con **Django Templates + Tailwind CSS + Alpine.js + HTMX** (sin overhead de builds complejas de Node/Webpack).
  - Plantilla base unificada con contenedor toast flotante de notificaciones (`messages.html`).
  - Drawer lateral desplegable por módulos (`drawer.html`).

---

## 2. Matriz de Arquitectura Implementada

| Ámbito | Mecanismo | Autenticación | Destinatarios | Formato Retorno | Estado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Portal Web Tallerista** | SSR (Templates + GPS PoPW) | Sesión Django (`/login/`) | Operario en taller (Celular/Desktop) | HTML responsivo (Tailwind) | **Completado** |
| **Backoffice ERP Comitente** | SSR (Templates + Leaflet.js) | Sesión Django (Staff/Interno) | Marca / Planta / Contabilidad | HTML responsivo | **Completado** |
| **Portal Fiduciario Clearing** | SSR (`fimca-core`) | Sesión Django / Staff | Auditor fiduciario / FIMCA | HTML (`clearing_dashboard.html`) | **Completado** |
| **Sincronización Federada M2M** | API REST / Webhooks | HMAC / API Key / Token | Nodos federados / FDI Central | JSON | **Completado** |
| **Tareas Asíncronas Celery** | Celery Beat | Interno (Redis) | Workers background | Tareas programadas | **Completado** |

---

## 3. Detalle de Fases Ejecutadas

### Fase A: Layout Base, Mensajes y Drawer Lateral
- **`templates/base.html`**:
  - Estilos responsivos con Tailwind CSS.
  - Inclusión de HTMX (`1.9.12`) con inyección de cabecera `X-CSRFToken`.
  - Inclusión de Alpine.js (`3.13.10`) para estado reactivo del drawer y auto-dismiss de mensajes.
- **`templates/includes/messages.html`**:
  - Toasts flotantes en la esquina superior derecha (`fixed top-4 right-4 z-50`).
  - Diferenciación cromática e iconografía para `success`, `error`, `warning` e `info`.
  - Auto-desvanecimiento a los 5 segundos con botón de cierre manual.
- **`templates/includes/drawer.html`**:
  - Menú lateral deslizable accesible desde el botón hamburguesa (`☰`).
  - Agrupación por aplicaciones: Producción & e-OP, Inventario, Contabilidad, Tesorería, Compras, Ventas, Contactos, Nómina y Administración.
- **Autenticación Unificada**:
  - `StyledLoginForm` y `RegistroTalleristaForm` (`apps/contactos/auth_forms.py`).
  - Vistas `LoginPortalView`, `LogoutPortalView`, `RegistroTalleristaView` (`apps/contactos/views.py`).
  - `HomeIndexView` (`core/views.py`): Despacho inteligente (si es tallerista externo ➔ redirige a `/produccion/portal-tallerista/`; si es usuario interno ➔ Dashboard `/`).

### Fase B: Portal Móvil del Tallerista (`apps/produccion/` y `apps/eop/`)
- **`apps/produccion/templates/produccion/portal_tallerista_list.html`**:
  - Vista mobile-first diseñada para el celular del operario.
  - Listado de etapas asignadas a su CUIT/CUIL con saldos pendientes.
  - **Prueba de Trabajo Físico (PoPW):** Captura en un clic de coordenadas GPS (`navigator.geolocation`) y almacenamiento como `Point(lng, lat, srid=4326)` en `OPParteProduccion.ubicacion_gps_declarada`.
  - **Módulo de Facturación y Cierre Fiscal (RCF):**
    - Muestra tarjeta de hito retenido con desglose de la **retención SIPA del 2%**.
    - **Botón "Emitir Factura C en 1-Click"**: Ejecuta `FacturacionAsistidaService.confirmar_y_emitir_factura_asistida` vía WSFEv1 de ARCA y destraba el hito.
    - **Modal "Cargar CAE Externo"**: Valida en vivo el comprobante mediante `FacturacionAsistidaService.constatar_factura_externa` (WSCDC) ante ARCA.

### Fase C: Vistas de la Marca Comitente y Módulos ERP
- **Contratos e-OP (`apps/eop/templates/eop/`)**:
  - `contrato_list.html`: Listado de títulos ejecutivos, estado de Escrows y régimen JIT.
  - `contrato_detail.html`: Panel de **Crédito Fiscal Presunto del 10% (Art. 23.1)** computable en el Libro IVA Digital (RG 4597), semáforo de mora en insumos JIT, standby devengado y control de hitos.
- **Producción (`apps/produccion/templates/produccion/`)**:
  - `op_list.html`: Órdenes de producción, balance de masa y sellos de protocolo e-OP.
  - `op_detail.html`: Trazabilidad territorial con **mapa interactivo de Leaflet.js** que renderiza el pin del taller (`Contacto.ubicacion_catastral`) y los puntos de avance PoPW.
- **Contabilidad & AFIP (`apps/contabilidad/templates/contabilidad/`)**:
  - `factura_list.html` y `factura_detail.html`: Comprobantes con CAE y exportación de Libro IVA.
- **Inventario (`apps/inventario/templates/inventario/`)**:
  - `quant_list.html`: Stock físico, reservas por orden y disponible.
  - `movimiento_list.html` y `movimiento_detail.html`: Kardex de stock y botón de transferencia física.
- **Tesorería (`apps/tesoreria/templates/tesoreria/`)**:
  - `comprobante_list.html` y `comprobante_detail.html`: Pagos de Escrow, movimientos de caja/banco y confirmación.
- **Compras, Ventas, Contactos y Nómina**:
  - `oc_list.html` y `oc_detail.html` (Compras e insumos).
  - `ov_list.html` y `ov_detail.html` (Ventas y pedidos).
  - `contacto_list.html`, `contacto_detail.html` y `contacto_form.html` (Directorio y alta de talleres).
  - `empleado_list.html`, `empleado_detail.html` y `empleado_egreso.html` (Nómina y liquidación final).

---

## 4. Estado de Validación Técnica
1. **Verificación Estática**: `uv run python manage.py check` con **0 errores** reportados tanto en `indinopy` como en `fimca-core`.
2. **Integridad de Base de Datos**: Cero migraciones nuevas generadas o requeridas.
3. **Desacople Fiscal Soberano**: Sin llamadas a intermediarios privados (`app.afipsdk.com`), usando directamente WSAA, WSFEv1 y WSCDC de ARCA.
