# Plan de Arquitectura e Implementación de Portales Web y Extranets - Indinopy

**Marco Normativo de Referencia:** [Anteproyecto de Ley e-OP (Octubre 2026)](../docs/md/proyecto_ley_eop.md) y Código Civil y Comercial de la Nación (CCyC)  
**Ubicación:** `utils/plan_portales_web_eop.md`  
**Estado:** En Planificación y Evolución Modular  
**Fecha:** Octubre de 2026  
**Entorno de Ejecución:** `indinopy` (ERP Centralizado en Marca + Extranets Ligeras) y `fimca-core` (Nodo Central Fiduciario y MES)  

---

## 1. Fundamentos y Principios de Arquitectura de Portales

1. **Instancia Única en la Marca:**  
   No se requiere ni se aconseja que talleres y proveedores monten servidores propios de Indinopy. La **marca comitente** opera su instancia central de Indinopy y expone portales web/móviles ligeros (extranets) optimizados para dispositivos móviles (PWA/SSR) con renderizado rápido mediante Django Templates, Tailwind CSS, Alpine.js y HTMX.

2. **Terminología Jurídica Estricta (Destierro del anglicismo "Escrow"):**  
   Conforme a la Ley e-OP y los Arts. 1666-1700 del CCyC, se elimina la palabra *"escrow"* del vocabulario funcional. Se utiliza:
   - **Liquidación fiduciaria de hitos productivos** / **Transferencias fiduciarias de fondos** desde las Cuentas Especiales de compensación y liquidación manufacturera en el Banco Central (BCRA, Art. 14°).
   - **Anticipo de Arranque (Hito Cero)** (35% estándar o 50% con Sello de Buen Diseño).
   - **Cancelación de Hitos de Avance**.
   - **Liberación de la Retención de Cierre Fiscal (RCF)** contra validación de CAE fiscal en ARCA.
   - **Órdenes de Pago Comercial (OPG)** para el circuito ordinario de compras.

3. **Separación Taxonómica de Actores Externos:**  
   - **Tallerista / Façonnier (Locación de Obra y Servicios de Confección):** No vende telas ni mercadería propia. Recibe materiales en custodia ($c_{\text{BOM}}$) y cobra por su mano de obra y capacidad industrial ($c_{\text{MOD}}$) mediante liquidación fiduciaria del FDI.
   - **Proveedor de Materiales (Compraventa Mercantil):** Vende cosas muebles (rollos de tela, avíos, hilos, botones, tintas, packaging) a la marca mediante Órdenes de Compra (OCs), emite facturas comerciales y cobra mediante Órdenes de Pago ordinarias de tesorería.
   - **Cliente B2B / Mayorista (Ventas):** Compra productos terminados a la marca mediante Órdenes de Venta (OVs). Pertenece a un portal de clientes completamente independiente (Cuentas por Cobrar y Catálogo).

---

## 2. Matriz de Arquitectura y Roles

| Portal / Módulo | Naturaleza Jurídica | Autenticación | Funcionalidades Principales | Estado |
| :--- | :--- | :--- | :--- | :---: |
| **Portal del Tallerista / Façonnier** (`/produccion/portal-tallerista/`) | Locación de Obra (Arts. 1251 y 1256 inc. a CCyC) y Custodia (Art. 1356 CCyC) | Sesión Django / CUIT (`Contacto.tipo in ['taller', 'ambos']`) | 1. Firma digital bilateral de e-OP (Clave Fiscal N3 / Ed25519)<br>2. Recepción de insumos en custodia y control JIT<br>3. Declaración de avance PoPW (GPS satelital)<br>4. Facturación asistida Factura C (2% SIPA) y seguimiento de liquidaciones fiduciarias del FDI | **Implementado (Fase 1)** |
| **Portal del Proveedor de Materiales** (`/compras/portal-proveedor/`) | Compraventa Mercantil (Arts. 1123 y ss. CCyC) | Sesión Django / CUIT (`Contacto.tipo in ['proveedor', 'ambos']`) | 1. Consulta y descarga de Órdenes de Compra (OCs en PDF)<br>2. Envío de remitos de entrega de insumos<br>3. Carga de Facturas comerciales (A/B) con validación de CAE ante ARCA<br>4. Consulta de estado de Órdenes de Pago (OPG) y fechas estimadas | **Planificado (Fase 2)** |
| **Backoffice ERP Marca Comitente** | Gestión Empresarial Interna | Django Staff / Roles internos | Moldería, producción, corte, órdenes de compra, stock, tesorería, contabilidad y libro IVA digital | **Implementado** |
| **Portal Fiduciario y Supervisión MES** (`fimca-core`) | Fideicomiso FDI y Comité MES | Sesión Django / Staff Fiduciario | Auditoría de carteras, timelock 48h, clearing masivo COELSA/BCRA, securitización Bonos BIP | **Implementado** |
| **Portal de Clientes B2B** (`/ventas/portal-cliente/`) | Compraventa de Productos Terminados | Sesión Django / CUIT (`Contacto.tipo in ['cliente']`) | Catálogo de colecciones, generación de Órdenes de Venta (OV), seguimiento de remitos de despacho, facturas de venta y recibos de cobro | **Planificado (Fase 3)** |

---

## 3. Detalle Funcional: Portal del Tallerista / Façonnier

El tallerista no es un vendedor de cosas, sino un locador de servicios productivos industriales:

### 3.1. Funcionalidades Activas
- **Declaración de Avance Físico con PoPW:** Captura obligatoria de coordenadas geodésicas en un clic (`navigator.geolocation`) persistidas como `PointField` en PostGIS dentro de `OPParteProduccion.ubicacion_gps_declarada`.
- **Cierre Fiscal y Facturación Asistida (RCF):**
  - Para monotributistas productivos (Art. 24.5 Ley e-OP): Generación asistida de Factura C con **retención del 2% SIPA** y emisión 1-click vía Web Service de Facturación Electrónica de ARCA (WSFEv1).
  - Para responsables inscriptos: Modal de carga de comprobante externo con constatación de CAE y parámetros fiscales en vivo ante ARCA vía WSCDC.
- **Rendimiento de Insumos Limitantes:** Bloqueo preventivo si el tallerista intenta declarar más unidades que las habilitadas por el insumo entregado según la receta técnica (BOM).

### 3.2. Mejoras a Incorporar en el Portal Tallerista
1. **Tarjeta de Contrato y Botón de Firma Digital e-OP:**
   - Incorporar en la cabecera del portal la visualización de los contratos e-OP pendientes de firma.
   - Botón interactivo para estampar la firma digital (Ed25519 / Clave Fiscal N3), ejecutando `AceptarContratoEOPActionView` para gatillar el timelock de 48h en el FDI.
2. **Semáforo de Logística Justo a Tiempo (JIT):**
   - Panel de insumos en custodia recibidos por remito.
   - Indicador de días de mora de la marca en la entrega de insumos con cálculo visible de la indemnización devengada por parada de planta (1 jornal diario SMVM a partir del 6° día hábil de demora).
3. **Monitoreo de Liquidación Fiduciaria:**
   - Tablero con el estado de cobro de cada hito: Hito Cero (Anticipo), Hitos de Avance y Retención de Cierre Fiscal (RCF), indicando fecha de acreditación fiduciaria en la cuenta bancaria informada.

---

## 4. Detalle Funcional: Portal del Proveedor de Materiales

El proveedor de materias primas (telas, avíos, hilados) opera bajo el circuito comercial de compras:

### 4.1. Arquitectura de URLs y Vistas
- **URL Base:** `/compras/portal-proveedor/`
- **Controlador Principal:** `PortalProveedorListView` (`apps/compras/views.py`):
  - Filtra órdenes de compra (`OrdenCompra`) donde `proveedor == request.user.perfil_contacto`.
  - Agrupa por estado: `pendiente_recepcion`, `recibido_parcial`, `facturado`, `pagado`.

### 4.2. Flujo Operativo del Proveedor de Materiales
1. **Recepción y Aceptación de Órdenes de Compra (OCs):**
   - El proveedor visualiza las OCs emitidas por la marca con especificación de artículos, cantidades pactadas y precios unitarios.
   - Descarga directa del PDF oficial de la OC mediante `OrdenCompraPDFDownloadView`.
2. **Notificación de Despacho y Remito:**
   - Formulario para cargar número de remito de entrega y fecha estimada de arribo a la planta de la marca.
3. **Carga y Vinculación de Factura Comercial:**
   - Formulario de carga de comprobante: Punto de Venta, Número de Comprobante, Fecha, Importe Total y CAE.
   - Validación automática contra el servicio de constatación de comprobantes de ARCA (WSCDC).
   - Creación automática del comprobante en `apps/contabilidad` vinculado a la OC correspondiente para aprobación de pagos.
4. **Consulta de Cuentas por Cobrar y Pagos:**
   - Listado de comprobantes de tesorería asociados: Órdenes de Pago (OPG) emitidas por la marca con detalle de retenciones impositivas (Ganancias, IIBB, IVA), fechas de acreditación bancaria y números de transferencia/cheque.

---

## 5. Detalle Funcional: Portal de Clientes B2B (Desacoplado)

Totalmente aislado de los portales de compras y confección para preservar el secreto comercial y la estructura de costos:

### 5.1. Arquitectura y Ámbito
- **URL Base:** `/ventas/portal-cliente/`
- **Controlador Principal:** `PortalClienteListView` (`apps/ventas/views.py`).
- **Destinatarios:** Locales comerciales, distribuidores, franquicias y clientes mayoristas (`Contacto.tipo == 'cliente'`).

### 5.2. Servicios Ofrecidos al Cliente
1. **Catálogo de Productos y Solicitud de Pedidos:**
   - Visualización de artículos terminados disponibles con curvas de talles y colores.
   - Generación de pedidos en borrador que ingresan a la marca como **Órdenes de Venta (OV)**.
2. **Seguimiento Logístico y Remitos de Entrega:**
   - Estado de preparación de pedidos, remitos de despacho y números de guía de transporte.
3. **Facturación y Descarga Fiscal:**
   - Descarga directa en PDF de las Facturas A/B emitidas por la marca con CAE oficial de ARCA.
4. **Estado de Cuenta Corriente:**
   - Consulta de saldo deudor/acreedor, vencimientos de facturas y descarga de Recibos de Cobro (RC) oficiales emitidos por la tesorería de la marca.

---

## 6. Hoja de Ruta de Implementación de Extranets

### Etapa 1: Consolidación del Portal del Tallerista (Completada en un 85%)
- [x] Autenticación y registro unificado (`LoginPortalView`, `RegistroTalleristaView`).
- [x] Despacho automático de inicio según rol (`HomeIndexView`).
- [x] Declaración de avances PoPW con coordenadas GPS satelitales.
- [x] Emisión 1-Click de Factura C asistida con 2% SIPA ante ARCA (WSFEv1).
- [x] Constatación de CAE externo ante ARCA (WSCDC).
- [ ] Incorporación de botón para estampar firma digital en contratos e-OP pendientes.
- [ ] Panel de visualización de semáforo JIT y standby devengado.

### Etapa 2: Desarrollo del Portal del Proveedor de Materiales (Próxima)
- [ ] Crear la vista `PortalProveedorListView` en `apps/compras/views.py`.
- [ ] Diseñar la plantilla `apps/compras/templates/compras/portal_proveedor_list.html`.
- [ ] Implementar la acción de carga y constatación de factura de insumos contra OC (`CargarFacturaOCActionView`).
- [ ] Exponer la consulta de Órdenes de Pago (OPG) y saldos a cobrar para proveedores.

### Etapa 3: Desarrollo del Portal de Clientes B2B (Futura)
- [ ] Crear la vista `PortalClienteView` en `apps/ventas/views.py`.
- [ ] Diseñar plantilla de catálogo y cuenta corriente de clientes.
- [ ] Habilitar consulta de Facturas de Venta emitidas y Recibos de Cobro.
