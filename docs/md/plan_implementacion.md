# Plan de Implementación — Indinopy ERP/MES
**Versión:** 0.1.0 | **Fecha:** Septiembre 2026  
**Autor:** Tiago Gabriel Sarthou

---

## Índice

1. [Visión del Proyecto](#1-visión-del-proyecto)
2. [Arquitectura del Sistema](#2-arquitectura-del-sistema)
3. [Estado Actual del Código](#3-estado-actual-del-código)
4. [Primitivas Criptográficas](#4-primitivas-criptográficas)
5. [Red Federada y Flujo de e-OP](#5-red-federada-y-flujo-de-e-op)
6. [Flujo del PTF (Promotor Territorial de Formalización)](#6-flujo-del-ptf-promotor-territorial-de-formalización)
7. [Traslado Escalonado de Insumos a Producción](#7-traslado-escalonado-de-insumos-a-producción)
8. [Roadmap de Implementación](#8-roadmap-de-implementación)
9. [Deuda Técnica Identificada](#9-deuda-técnica-identificada)
10. [Referencias](#10-referencias)

---

## 1. Visión del Proyecto

Indinopy es un **ERP/MES para PyMEs de la industria del calzado y la indumentaria argentina**, construido sobre el protocolo de **Órdenes de Producción Electrónicas (e-OP)** que funcionan como **activos fiduciarios negociables**.

### Principios Fundamentales

- **La e-OP es inmutable.** Una vez confirmada y sellada con su hash criptográfico, sus términos económicos no pueden modificarse unilateralmente.
- **La Custodia / Escrow es la garantía.** Los fondos de capital de trabajo y liquidaciones adelantados por el FDI quedan asegurados en una cuenta de custodia digital hasta que se certifica y libera el hito correspondiente.
- **La confianza es matemática, no institucional.** El sistema no confía en la palabra de ningún actor. Confía en firmas Ed25519 verificables y hashes SHA-256 deterministas.
- **El Silencio es Positivo.** Si en 48 horas ningún miembro de la MES vetó una e-OP, el sistema la aprueba automáticamente sin intervención humana (Timelock).

### Actores del Sistema

| Actor | Rol | Nodo |
|---|---|---|
| **Comitente (Marca)** | Genera la e-OP, aporta garantía de anclaje y cancela el crédito a 30-60 días | ERP propio (Indinopy) |
| **Tallerista** | Ejecuta la producción, firma aceptación | ERP propio (Indinopy) |
| **PTF** (Promotor Territorial de Formalización) | Auditor de campo, firma la liberación del Escrow | App móvil + Nodo MES |
| **Mesa de Enlace Sectorial (MES)** | Gobernanza, homologa PTFs, administra Timelock | Nodo central compartido |
| **Fiduciaria (FDI)** | Administra el fondo de liquidez y anticipa fondos por hitos | Integración externa |

### Premisa de Alcance: Soporte Integral a la Marca Manufacturera

La arquitectura y las prioridades de desarrollo de Indinopy responden a una premisa clara: **dar soporte en primera instancia a la Marca/Fábrica comitente**, y en **segunda instancia al Tallerista satélite**:
* **Cobertura 360° de la Marca:** El ERP resuelve la operación integral de una fábrica real: manufactura física en planta propia (BOM, recetas, órdenes internas de corte y armado), liquidación de nómina de operarios directos bajo convenio (UTICRA / SOIVA con Libro de Sueldos Digital ARCA y aprobación dual SoD), contabilidad por partida doble e IVA Digital, y tesorería comercial (cobranzas WooCommerce/Mercado Pago y repago diferido al FDI).
* **Impermeabilidad de Nómina y Blindaje Laboral:** La nómina de la marca (`apps.nomina`) es estrictamente hermética. Los operarios y destajistas de talleres periféricos jamás figuran en los libros de sueldos de la marca, blindando la operación frente a la presunción de solidaridad laboral (Art. 30 LCT).
* **Integración Satélite del Taller:** El tallerista se integra en segunda instancia mediante una interfaz ligera (Portal web PWA móvil con ficha técnica ciega de costos y firma Ed25519) sin necesidad de infraestructura propia, o mediante un nodo federado autónomo si se trata de un taller consolidado o cooperativa. Los fondos de la e-OP son fondeados directamente por el FDI, sin que la marca deba desembolsar caja operativa propia durante la fabricación.

---

## 2. Arquitectura del Sistema

### Stack Tecnológico

```
Backend:        Django 6.1 (MVT + REST API)
Servidor Web:   Uvicorn (ASGI) / Gunicorn (WSGI)
Base de Datos:  PostgreSQL 16 + PostGIS (coordenadas GPS)
ORM History:    django-simple-history (auditoría inmutable)
Criptografía:   hashlib (SHA-256) + PyNaCl (Ed25519)
Geoespacial:    django.contrib.gis (PointField, MultiPolygonField)
Facturación:    afip-py (WSFE/WSFEX)
E-Commerce:     WooCommerce REST API v3 (Webhooks + Polling)
Async / Tareas: Celery + Redis 7 (Timelock 48h y encolamiento de Webhooks masivos)
Contenedores:   Docker (Dockerfile multi-stage) + Docker Compose
```

### Patrones de Despliegue de Infraestructura y Enrutamiento

1. **SaaS (Servidor Comunitario / Multi-Tenant):** Despliegue recomendado en un VPS de entrada (2 vCPUs, 4GB RAM) alojado por la Cámara o el CIFO de un municipio. 
   - **Enrutamiento DNS Jerárquico:** El nodo MES local gestiona la subzona delegada `{municipio}-mes.indinopy.ar`. Las fábricas acceden a su propio inquilino a través del Nivel 3: `{marca}.{municipio}-mes.indinopy.ar`.
   - **Manejo de Carga:** Al operar con WooCommerce, utiliza **Redis y Celery** para absorber picos de tráfico (Efecto HotSale) sin saturar el servidor web.
2. **On-Premise (PC en el Taller):** Instalación en una PC estándar de la fábrica. Dado que los routers de fábrica bloquean conexiones entrantes, se conecta a la Red Federada y a WooCommerce mediante **Polling** (el Nodo consulta novedades cada 5 minutos de forma silenciosa) o **Túneles Inversos** (ej. Cloudflare Tunnels) para recibir webhooks en tiempo real sin abrir puertos.

### Patrón Arquitectónico: Capa de Servicios (Service Layer)

```
HTTP Request
     ↓
 [View / CBV]         ← Solo recibe, valida y redirige. Sin lógica de negocio.
     ↓
[Service Layer]       ← Toda la lógica transaccional. Usa transaction.atomic().
     ↓
  [Models]            ← Solo estructura de datos y validaciones de campo.
     ↓
[Signals]             ← Solo eventos secundarios (logs, notificaciones). Sin lógica financiera.
```

**Regla de oro:** Nunca cambiar el estado de una e-OP haciendo `op.estado = 'confirmado'; op.save()`.  
Siempre usar `ProduccionService.confirmar_op(op)`.

### Módulos y Responsabilidades

| App | Responsabilidad | Service |
|---|---|---|
| `base` | Mixins criptográficos, ConfiguracionEmpresa, secuencias alfanuméricas, BaseReports | `SecuenciaService` |
| `contactos` | Directorio de Clientes, Proveedores, Talleristas, geocercas GPS | `ContactosService` |
| `inventario` | Stock en tiempo real (Quants, doble entrada, remitos de traslado/entrega) | `StockService` |
| `produccion` | e-OP, BOM, Recetas, Etapas MES, rendimientos y mermas | `ProduccionService` |
| `compras` | Solicitudes de Cotización (RFQ), Órdenes de Compra, Tarifas, 3-Way Matching | `ComprasService` |
| `ventas` | Presupuestos, Notas de Pedido, Órdenes de Venta omnicanal, Remitos | `VentasService` |
| `integraciones` | Adaptadores satélite externos (`woocommerce` con normalizador DTO) | `WooCommerceNormalizer`, `tasks` |
| `afip` | Conector oficial AFIP/ARCA (Padrón WSSR, Facturación WSFE/WSFEX, QR fiscal) | `PadronAFIPService`, `FacturadorAFIP` |
| `contabilidad` | Partida Doble, Facturación A/B/C/X, Deudas, Convenio Multilateral CM05/CM03 | `ContabilidadService` |
| `tesoreria` | Escrow Digital, Cajas, Comprobantes, Títulos FCE | `EscrowService`, `TesoreriaService` |
| `eop` | Contratos e-OP fiduciarios, hitos de clearing, verificación de avance | `EOPService` |
| `mes` | Gobernanza MES, RegistroEOP, PTF, Timelock 48h | `PTFService` |

---

## 3. Estado Actual del Código

### ✅ Implementado

#### Modelos Core
- **Desacople Arquitectónico (App `eop`)**: Separación estricta de dominios (Domain-Driven Design). La lógica fiduciaria de la Orden de Producción Electrónica reside exclusivamente en `apps.eop`, manteniendo `produccion` y `tesoreria` agnósticos.
- `OrdenProduccion` — Módulo industrial puro.
- `ContratoEOP` + `EOPHitoEscrow` — Contrato de custodia digital y administración fiduciaria (en `eop`).
- **Retención Fiscal (`FISCAL_PENDING`)**: Estado inyectado en `EOPHitoEscrow` (`requiere_verificacion_arca`). El Fideicomiso no libera el último 20% del pago hasta que el tallerista emite la factura electrónica en ARCA (ex-AFIP), previniendo la defección fiscal.
- `OPEtapaTracking` — **Lógica de Avance Proporcional Abstracta**. Bloqueos matemáticos just-in-time que impiden a un tallerista declarar avances físicos si la etapa previa no habilitó las unidades suficientes, aplicable a cualquier industria.
- `StockQuant` — Foto en tiempo real del stock (partida doble).
- `MovimientoStock` + `LineaMovimientoStock` — Motor de doble entrada.
- `Contacto` con `ubicacion_catastral` (GPS), `es_taller_homologado`, `ucp_score`.
- **Motor de Secuencias Alfanuméricas (`apps.base`)**: Implementado motor centralizado con `select_for_update()` para evitar colisiones de concurrencia. Los modelos como `OrdenProduccion`, `MovimientoStock`, y `ComprobanteTesoreria` heredan dinámicamente de `DocumentoBase` determinando su sufijo fiscal o interno al vuelo.

#### Gobernanza y Criptografía (Módulo Federación / MES)
- `RegistroEOP` — Copia canónica en el nodo MES con Timelock.
- `ComisionCredito`, `PerfilPTF`, `ResolucionOP`, `TribunalArbitraje` — Modelos de gobernanza.
- `PTFService` — Verificación de firmas en campo y certificados canónicos (Ed25519 con PyNaCl implementado al 100%).
- `PTFService` — Control espacial Point-in-Polygon (PostGIS) de zonas de cobertura.
- `PTFService` — Lógica de aprobación exprés, veto de e-OPs y Silencio Positivo (Timelock 48h).

#### Capa de Servicios y Background Tasks
- `EOPService.procesar_eop()` / `fondear_escrow()` / `liberar_hito()` — Transacciones fiduciarias aisladas. Modificado para no tocar caja local; la liquidación de hitos y el fondeo (Factoring Hito Cero) los realiza exclusivamente el FDI.
- `EOPService.firmar_contrato_tallerista()` — Sello de identidad local previo a envío a la MES.
- `constatar_facturas_arca_pendientes()` — Celery Task que hace polling automático contra AFIP para destrabar hitos en `FISCAL_PENDING`.
- Signals en `eop/signals.py` — Puente asíncrono para coordinar avances físicos con auditorías PTF.
- `StockService.reservar_linea()` / `realizar_linea()` / `cancelar_linea()`
- `ProduccionService.confirmar_op()` / `finalizar_op()` / `cancelar_op()` (Auditoría: se evita la duplicación de deuda en OPs federadas).
- `ComprasService.confirmar_oc()` / `cancelar_oc()`
- `VentasService.procesar_orden_woocommerce()` / `procesar_producto_woocommerce()`

#### Vistas (CBVs), Enrutamiento y API Federada
- Pattern ListViews + DetailViews en todos los módulos (incluyendo la nueva app `eop` y `tesoreria`).
- Action Views fiduciarios: `AceptarContratoEOPActionView` (firma tallerista), `CargarFacturaHitoActionView` (destrabe manual ARCA).
- **Webhooks Federados**: `MESWebhookHitoLiberadoAPIView` y `MESWebhookContratoFondeadoAPIView` listos para recibir instrucciones PUSH de fondeo y pago desde el Fideicomiso (vía MES) hacia el ERP local.
- Enrutamiento modular (incluyendo `eop/urls.py`, `tesoreria/urls.py`) registrado en `core/urls.py`.

#### Integraciones Externas y Omnicanalidad (`apps.integraciones.woocommerce`)
- Desacople integral de `apps.ventas` mediante DTOs agnósticos (`OrdenVentaDTO`, `ClienteDTO`, `LineaOrdenDTO`, `RecargoDTO`, `EnvioDTO`, `CuponDTO`).
- Modelo `CanalVenta` en `apps.ventas` con persistencia de `referencia_externa` y clave de canal.
- Aplicación satélite `apps.integraciones.woocommerce` con modelo `TiendaWooCommerce`, endpoints de webhooks con validación HMAC-SHA256, cliente REST API v3 y tareas asíncronas de Celery (`tasks.py`).
- Normalizador agnóstico `WooCommerceNormalizer` y sincronización bidireccional de productos, precios, cupones y stock disponible (`StockQuant`).

#### Facturación AFIP y Títulos FCE
- `apps.afip` — Módulo desacoplado para servicios fiscales de AFIP/ARCA.
- `AFIPClientFactory` — Singleton centralizado de autenticación y certificados X.509.
- `PadronAFIPService` — Consulta de Padrón Tributario WSSR con caché Redis de 24 horas y sincronización con `Contacto`.
- `FacturadorAFIP.validar_compatibilidad_fiscal()` — Validación estricta y previa entre condición IVA del emisor (`ConfiguracionEmpresa`) y receptor (`Contacto`), impidiendo la emisión de comprobantes A/B/C incompatibles.
- `AFIPQRGenerator` — Generador de código QR oficial en Data URI Base64 según Resolución General 4291/2018.
- `TituloCreditoFCE` — Administración de Factura de Crédito Electrónica MiPyME (Ley 27.440) en `apps.tesoreria`, con control de los 21 días de plazo y circulación (SCA / ADC).

#### Arquitectura de Reportes y Documentos
- Motor base universal desacoplado en `apps/base/reports/base.py`:
  - `BaseReport`: Protocolo agnóstico con generación a bytes y exportación a HttpResponse.
  - `BasePDFReport`: Renderizado HTML/CSS Paged Media con soporte WeasyPrint y fallback imprimible en navegador.
  - `BaseTabularReport`: Generación de planillas Excel `.xlsx` corporativas (`openpyxl`) con fallback a CSV delimite `;` y BOM UTF-8 regional.
  - **Criterio de Diseño Unificado:** Estandarización tipográfica y estética en todos los comprobantes PDF (geometría A4, márgenes de 10mm/12mm, tipografía Arial/Slate-900 `9pt`, cabecera institucional perimetral de dos columnas, cajas `.info-box` con fondo `#f8fafc`, tablas `.tabla-items` con encabezado institucional oscuro o verde esmeralda, y totales `.total-destacado`).
- **Remito Oficial de Logística** (`apps/inventario/reports/remito_report.py`):
  - Soporta tres modalidades operativas: Remito de Entrega a Clientes (Ventas), **Remito de Traslado a Producción** (Talleres/Fasón con inyección obligatoria de la cláusula de custodia e inembargabilidad Arts. 1251 y 1356 CCCN) y Traslados Internos entre depósitos.
- **Inventario y Trazabilidad:**
  - `InventarioStockExcelReport` (`apps/inventario/reports/inventario_stock_report.py`): Foto de existencias físicas, reservas comprometidas, stock neto disponible y valuación económica por almacén y lote.
  - `MovimientosStockExcelReport` (`apps/inventario/reports/movimientos_stock_report.py`): Kardex general y trazabilidad cronológica de remitos por partida doble.
- **Módulo de Compras:**
  - `OrdenCompraPDFReport` (`apps/compras/reports/orden_compra_report.py`): Documento formal de compra valorizado con desglose de IVA y términos de recepción.
  - `SolicitudCotizacionPDFReport` (`apps/compras/reports/solicitud_cotizacion_report.py`): Solicitud de Cotización / Presupuesto a Proveedores (RFQ) sin compromiso de compra ni exposición de precios de catálogo, con campos para cotización de precio y validez.
  - `RecepcionesPendientesExcelReport` (`apps/compras/reports/recepciones_pendientes_report.py`): Reporte tabular de abastecimiento (Backorders de Compras) que monitorea cantidades pedidas vs recibidas y demoras en días.
- **Módulo de Ventas:**
  - `PresupuestoPDFReport` (`apps/ventas/reports/presupuesto_report.py`): Renderiza dinámicamente Presupuestos / Cotizaciones Comerciales (con fecha de validez y cláusula de no reserva de stock) o Notas de Pedido en firme.
- **Módulo Contable y Fiscal:**
  - `LibroIVAVentasExcelReport` (`apps/contabilidad/reports/libro_iva_report.py`): Planilla fiscal con desglose oficial de alícuotas AFIP, notas de crédito y percepciones.
  - `LibroIVAComprasExcelReport` (`apps/contabilidad/reports/libro_iva_report.py`): Liquidación mensual de crédito fiscal y percepciones sufridas (IIBB e IVA).
  - `ConvenioMultilateralCoeficientesReport` (`apps/contabilidad/reports/convenio_multilateral_report.py`): Matriz CM05 anual (50/50 ingresos y gastos computables Art. 3 CM) y anticipos provinciales CM03 por código SIFERE.
  - `ComprobanteFiscalPDFReport` (`apps/contabilidad/reports/comprobante_report.py`): Facturas A/B/C, NC, ND y Comprobantes X con QR oficial ARCA, Transparencia Fiscal Ley 27.743 y cláusulas FCE.
  - *(Roadmap)* `LibroDiarioGeneralReport`: Cronológico de asientos contables cuadrados (`Asiento` / `Apunte`) por rango de fechas y diarios.
  - *(Roadmap)* `LibroMayorExcelReport`: Mayores auxiliares analíticos con saldo progresivo por cuenta contable.
  - *(Roadmap)* `BalanceSumasYSaldosReport`: Balance de comprobación de 8 columnas (Sumas Debe/Haber y Saldos Deudor/Acreedor) para auditoría de cierre.
- **Módulo de Tesorería y Cobranzas/Pagos:**
  - *(Roadmap)* `OrdenPagoReciboPDFReport` (`apps/tesoreria/reports/comprobante_tesoreria_report.py`): Recibos de cobranza a clientes y Órdenes de Pago a proveedores con desglose de medios de cobro/pago (efectivo, transferencias, retenciones, e-cheqs) y aplicaciones contra comprobantes devengados.
  - *(Roadmap)* `CertificadoRetencionPDFReport` (`apps/tesoreria/reports/certificado_retencion_report.py`): Certificados oficiales de retención practicada (Ganancias / IVA / IIBB) con número correlativo y base imponible.
  - *(Roadmap)* `CashflowProyectadoExcelReport` (`apps/tesoreria/reports/cashflow_report.py`): Posición diaria/semanal de liquidez consolidando saldos en cuentas/cajas, vencimientos de cartera de cheques propios/terceros y deuda corriente.
  - *(Roadmap)* `CarteraChequesExcelReport` (`apps/tesoreria/reports/cartera_cheques_report.py`): Padrón y trazabilidad de cheques físicos y E-cheqs agrupados por estado (`en_cartera`, `depositado`, `entregado`) y fecha de cobro diferido.
  - *(Roadmap)* `DeudaCorrienteAgingExcelReport` (`apps/tesoreria/reports/deuda_aging_report.py`): Antigüedad de saldos a cobrar y a pagar (corriente, 30, 60, 90+ días) basado en `DocumentoDeuda` y condiciones de pago.
- **Módulo de Nómina y Recursos Humanos (`apps.nomina`):**
  - *(Roadmap)* `ReciboSueldoPDFReport` (`apps/nomina/reports/recibo_sueldo_report.py`): Recibo formal de haberes (A4 doble vía / duplicado) con discriminación de conceptos remunerativos, no remunerativos, retenciones de ley, Fondo de Cese Laboral (Ley Bases) y firma del empleado.
  - *(Roadmap)* `LibroSueldosDigitalTxtReport` (`apps/nomina/reports/lsd_report.py`): Exportador oficial de texto de longitud fija para ARCA (Registros 1 Cabecera, 2 Datos Trabajador/Bases Imponibles, 3 Conceptos y 4 Relación Laboral).
  - *(Roadmap)* `LiquidacionNominaExcelReport` (`apps/nomina/reports/liquidacion_excel_report.py`): Planilla mensual consolidada de haberes, retenciones de empleados y costo patronal total de la empresa (F931 + ART + Fondo Cese).
  - *(Roadmap)* `AcreditacionHaberesTxtReport` (`apps/nomina/reports/acreditacion_haberes_report.py`): Archivo plano estándar de transferencias masivas a cuentas sueldo bancarias (Galicia, Santander, Red Link / Interbanking).
- **Módulo de Producción Industrial (`apps.produccion`):**
  - *(Roadmap)* `OrdenProduccionPDFReport` (`apps/produccion/reports/op_report.py`): Hoja de Ruta de Planta con código de barras/QR de la OP, curva de talles desagregada por variación, ficha técnica de la receta (BOM) y checklist de etapas operativas.
  - *(Roadmap)* `BOMExplosionReport` (`apps/produccion/reports/bom_explosion_report.py`): Explosión de materiales y avíos requeridos para el lote o tanda, confrontando consumo teórico vs existencias en almacén.
  - *(Roadmap)* `RendimientoProduccionExcelReport` (`apps/produccion/reports/rendimiento_report.py`): Matriz de desvíos y rendimiento industrial con comparación de consumo teórico vs real (`cantidad_consumida_real`) y alertas de exceso de merma (>10%).
  - *(Roadmap)* `LiquidacionFasonExcelReport` (`apps/produccion/reports/liquidacion_fason_report.py`): Detalle para talleres externos de pares de 1ra y 2da selección producidos y servicios prestados a liquidar.

#### Modelo de Producción y Validaciones JiT de Avance
- Techo de Rendimiento Estequiométrico (`capacidad_maxima_por_insumos` en `OPEtapaTracking`): el avance físico de la etapa inicial queda condicionado matemáticamente a la materia prima en custodia despachada al taller mediante remito JiT ($E_{\text{net}} \le V_{\text{fase}}$).
- Circuitos de entregas parciales y recepción física en planta con discriminación de 1ra, 2da selección y descarte.

#### Segregación de Funciones (SoD) y Grupos de Permisos Django
Para garantizar la integridad operativa y mitigar riesgos de fraude interno, el sistema estructura la autorización mediante grupos de Django predeterminados (Data Fixture / Seed):
* **Alta Gerencia / Apoderado Legal:** Único rol habilitado para constituir garantías crediticias y firmar con Ed25519 el payload canónico de la e-OP.
* **Jefe de Producción:** Administración de Recetas (BOM), lanzamiento de OPs y planificación MRP. *Bloqueo duro:* Sin acceso a firmas fiduciarias.
* **Jefe de Compras y Almacén:** Emisión de OC a proveedores, recepción de insumos y remitos de traslado en custodia hacia talleres (`TRA-...`).
* **Ventas y Canales:** Gestión comercial y multitienda (`CanalVenta`, `TiendaWooCommerce`). *Bloqueo duro:* Sin visualización de costos industriales (`view_costos_op`).
* **Finanzas y Tesorería:** Administración de cajas, cuentas bancarias, valores y emisión de Órdenes de Pago para repago del crédito al FDI (`escrow_asociado`).
* **Contabilidad:** Registro del devengado, conciliación bancaria, IVA Digital y liquidación de impuestos (SICORE/SIFERE).
* **Recursos Humanos:** Legajos, licencias, novedades variables y liquidación de sueldos (LSD ARCA). *Bloqueo duro (SoD):* Requiere aprobación dual de Tesorería (`aprobador_tesoreria`) para autorizar el desembolso bancario.

> 🔗 Para consultar la matriz de responsabilidades y segregación de funciones, ver: [`docs/roles.html`](roles.html).


## 4. Primitivas Criptográficas

### SHA-256 (Hash de Integridad)
Cada e-OP genera un **payload canónico determinista** (JSON ordenado por claves) y lo hashea con SHA-256. Este hash se sella en el campo `hash_seguridad` al confirmar la orden. Cualquier modificación posterior produce un hash diferente, evidenciando la manipulación.

### Árbol de Merkle (Integridad del BOM)
Los insumos del BOM se hashean individualmente y se combinan en pares hasta obtener el `merkle_root_bom`. Esto permite auditar que un insumo específico no fue alterado sin necesidad de revelar toda la receta.

### Ed25519 (Firmas Digitales Multifirma)
El campo `firmas_digitales` (JSONField) almacena las firmas de cada rol:
```json
{
  "comitente": {
    "actor_id": 12,
    "firma_hex": "a3f9c8d2...",
    "timestamp": "2026-09-09T18:30:15Z"
  },
  "ptf": {
    "actor_id": 7,
    "firma_hex": "7b12e4a9...",
    "timestamp": "2026-09-09T20:45:00Z"
  }
}
```
`django-simple-history` toma un snapshot inmutable del documento en cada firma, creando una cadena de evidencia auditable.

> **Implementado:** La verificación matemática Ed25519 con la librería `PyNaCl` ya se encuentra plenamente integrada en `PTFService` y los Webhooks de la red.

---

## 5. Red Federada y Flujo de e-OP

### Modelo de Confianza: PKI Federada

La MES actúa como **Autoridad Certificante (CA)** de la red. Cada nodo recibe la clave pública de la MES al registrarse. Con ella puede verificar cualquier certificado emitido por la MES **sin conexión en tiempo real**.

```
MES (CA Root)
├── Certificado Nodo Comitente A  [firmado con MES_privada]
├── Certificado Nodo Tallerista B [firmado con MES_privada]
├── Certificado PTF Carlos        [firmado con MES_privada]
└── Certificado PTF Ana           [firmado con MES_privada]
```

### Flujo Completo de una e-OP

```
[NODO COMITENTE]
  1. Crea e-OP en borrador
  2. ProduccionService.confirmar_op():
     - Calcula BOM + Merkle Root
     - Sella hash SHA-256
     - Genera ContratoEscrow
     - Comitente firma con su Ed25519 privada
  3. POST → Nodo MES: payload canónico + firma_comitente

[NODO MES]
  4. Verifica firma_comitente (Ed25519 vs clave pública del Comitente)
  5. Crea RegistroEOP → estado: "en_revision"
  6. Inicia Timelock de 48h (worker Celery)
  7. POST → Nodo Tallerista: payload canónico de la e-OP
  8. PUSH → App PTF de la zona: notificación de auditoría pendiente

[NODO TALLERISTA]
  9. Recibe e-OP entrante
  10. Verifica: hash_recibido == SHA-256(payload_recibido)
  11. Acepta y firma con su Ed25519 privada
  12. POST → Nodo MES: firma_tallerista

[PTF EN CAMPO]
  13. Va físicamente al taller
  14. App móvil:
      - GPS confirma radio del taller catastral (PostGIS)
      - Biometría desbloquea clave Ed25519 del Secure Enclave
      - Firma: hash(e-OP + GPS + timestamp)
  15. POST → Nodo MES: { firma_ptf, certificado_ptf, gps, timestamp }

[NODO MES — Resolución]
  16. Verifica firma_ptf con clave pública del certificado PTF
  17. Verifica certificado PTF no revocado (CRL)
  18. Verifica GPS en zona de cobertura del PTF
  19. Verifica timestamp dentro del Timelock
  20. RegistroEOP → estado: "aprobado_expres"
  21. POST → Fiduciaria: liberar fondos del Escrow
  22. POST → Nodo Comitente + Tallerista: confirmación de pago

[CASO SILENCIO POSITIVO]
  Celery Beat ejecuta cada hora:
  - Busca RegistroEOP con timelock_vencimiento <= now()
  - Si no hay vetos ni ResolucionOP → aprobado_silencio
  - Dispara liberación automática del Escrow
```

### El Sistema Dual (OP Privada vs e-OP Federada)

Para no burocratizar el uso diario de las PyMEs, Indinopy cuenta con un **Sistema Dual** controlado por la bandera `es_eop_federada`:
- **OP Privada (Simple):** No requiere MES, PTF, Timelock ni Escrow. Las etapas se avanzan internamente por sistema generando una simple *Cuenta por Pagar* para el taller, que el Tesorero de la marca cancela manualmente mediante transferencias tradicionales. Permite el uso de Cajas No Fiscales y Comprobantes X para la gestión del flujo real no formalizado.
- **e-OP Federada (FIMCA):** Engancha el Smart Contract, bloquea los fondos en el Fideicomiso y transfiere automáticamente a través del Banco Provincia o entidad fiduciaria mediante el sistema de clearing cuando se valida la firma de la etapa.

### Formalización Automática: Alta de Oficio en la Primera e-OP

El software elimina la barrera burocrática del tallerista informal o trabajador de oficio que carece de CUIT o Clave Fiscal:

#### 1. Inyección en el Payload Canónico de la e-OP
Cuando la marca emite o el tallerista confirma su primera e-OP, si el tallerista asignado a una etapa (o el Taller Gestor) no cuenta con inscripción fiscal activa en el padrón de la MES, el ERP emisor inyecta los datos de onboarding directamente en el payload canónico que viaja al Nodo MES:

```json
{
  "protocolo_version": "2.0",
  "uuid_identificador": "e8b7c934-8fa4-4e1a-ad35-c02cd6ac65d1",
  "comitente": {
    "cuit": "30-71589412-8",
    "cbu_comercial": "0140098701509900412891"
  },
  "taller_gestor": {
    "denominacion": "Taller San Cayetano (Consorcio Lanús)",
    "cuit_gestor": "20-18493021-3",
    "estado_societario": "transicion_sas",
    "cuenta_clearing_cvu": "0000003100094182901412"
  },
  "etapas_asignadas": [
    {
      "orden": 1,
      "servicio": "Corte",
      "tallerista": {
        "cuit": "30-68912345-2",
        "tipo": "taller_homologado",
        "cuenta_clearing_cvu": "0140023401100984210019"
      }
    },
    {
      "orden": 2,
      "servicio": "Aparado",
      "tallerista": {
        "dni": "28451902",
        "tipo": "prestador_oficio",
        "requiere_alta_oficio": true,
        "datos_alta_oficio": {
          "nombre_completo": "Carlos Alberto Benegas",
          "biometria_token_renaper": "0x7a91...bc01",
          "cvu_cuenta_dni": "0000003100094182901412",
          "domicilio_catastral": "Pasaje Ucrania 1420, Lanús Oeste",
          "actividad_codigo": "152011"
        }
      }
    }
  ]
}
```

#### 2. Capa de Servicios: `AltaOficioService` (`apps.federacion.services`)
Al recibir el payload canónico, el Nodo MES ejecuta el pipeline transaccional de formalización:
1. **Validación Biométrica RENAPER:** Valida la identidad y prueba de vida del titular contra el servicio nacional del RENAPER usando el token biométrico capturado en la app/portal.
2. **Alta Automática en ARCA (ex-AFIP):** Invoca el webservice de Monotributo Productivo de Oficio. El tallerista queda formalizado sin cuota fija mensual que lo endeude cuando no tiene trabajo; en su lugar, se activa la micro-retención del 1.5% en clearing.
3. **Apertura de Cuenta de Clearing Técnica Inembargable (BAPRO):** Vía Open Banking del Banco Provincia, se genera o vincula la cuenta de clearing (Cuenta DNI / CVU) con el flag legal de inembargabilidad absoluta de primer orden amparado en CCCN 1356.
4. **Emisión de Par de Claves Ed25519:** La MES firma digitalmente el certificado público del tallerista y lo incorpora al padrón activo de la federación.

### Especificación del Contrato API: Sobre de Red y Payload Canónico Completo

Cuando el ERP de la Marca (Nodo Comitente) confirma una e-OP y la transmite a la MES (`POST /federacion/eop/entrante/`), la comunicación consta de dos capas estrictas:

#### 1. Sobre de Transporte Criptográfico (`EntradaEOPSerializer`)
Es el payload HTTP que recibe y valida el API Gateway de la MES para autenticación, no repudio y anti-tampering:

```json
{
  "uuid_identificador": "e8b7c934-8fa4-4e1a-ad35-c02cd6ac65d1",
  "hash_seguridad": "a4f81c7b8e923d456102fae83912bc09148d200126d482910384729104829104",
  "comitente_cuit": "30715894128",
  "tallerista_cuit": "20184930213",
  "monto_total_uci": "3950.0000",
  "clave_publica_comitente": "7d9b01f92c3a4e5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b",
  "firma_comitente": "3a8f10bc49281e...[firma Ed25519 en hex de 128 caracteres]...",
  "payload_canonico": { ... }
}
```

#### 2. Payload Canónico Determinista (`payload_canonico`)
Es el contrato fiduciario inmutable que se firma digitalmente con Ed25519 y cuyo hash SHA-256 se sella en la red:

```json
{
  "protocolo_version": "2.0",
  "uuid": "e8b7c934-8fa4-4e1a-ad35-c02cd6ac65d1",
  "numero_op": "OP-2026-00842",
  "fecha_emision": "2026-09-09T09:30:00Z",
  "partes": {
    "comitente": {
      "cuit": "30-71589412-8",
      "razon_social": "Borcegos Cruz del Sur S.R.L.",
      "cbu_comercial": "0140098701509900412891",
      "plazo_cancelacion_fdi_dias": 60
    },
    "taller_gestor": {
      "cuit_o_dni": "20-18493021-3",
      "denominacion": "Taller San Cayetano (Consorcio Lanús)",
      "estado_societario": "transicion_sas",
      "cuenta_clearing_cabecera": "0000003100094182901412"
    }
  },
  "condiciones_economicas": {
    "moneda_indexacion": "UCI",
    "monto_total_uci": 3950.00,
    "desglose_vector_c": {
      "costo_mod": 2825.00,
      "costo_cs": 565.00,
      "reserva_fdi": 79.00,
      "monotributo_retencion": 59.25,
      "margen_taller": 421.75
    },
    "es_sello_buen_diseno": true,
    "timelock_horas": 48
  },
  "cronograma_escrow_hitos": [
    {
      "id_hito": "H0",
      "nombre": "Adelanto Operativo / Hito Cero",
      "porcentaje_tramo": 40.0,
      "condicion_disparo": "Aprobacion_MES_o_Silencio_48h",
      "destinatario": "taller_gestor"
    },
    {
      "id_hito": "H1",
      "nombre": "Corte Completo y Verificado",
      "porcentaje_tramo": 20.0,
      "condicion_disparo": "PoPW_Parte_Corte_Mas_Aval_PTF",
      "destinatario": "etapa_corte"
    },
    {
      "id_hito": "H2",
      "nombre": "Aparado Terminado",
      "porcentaje_tramo": 25.0,
      "condicion_disparo": "PoPW_Remito_Traslado_Aparado",
      "destinatario": "taller_gestor"
    },
    {
      "id_hito": "H3",
      "nombre": "Liquidación Cierre de Lote",
      "porcentaje_tramo": 15.0,
      "condicion_disparo": "Recepcion_Conforme_Sin_Veto_48h",
      "destinatario": "taller_gestor"
    }
  ],
  "etapas_productivas": [
    {
      "orden": 1,
      "servicio": "Corte de Cuero y Forro",
      "tallerista_asignado": {
        "cuit": "30-68912345-2",
        "nombre": "Cortaduría El Ombú",
        "cuenta_clearing_cvu": "0140023401100984210019",
        "tipo": "taller_homologado"
      }
    },
    {
      "orden": 2,
      "servicio": "Aparado Reforzado",
      "tallerista_asignado": {
        "cuit": "20-18493021-3",
        "nombre": "Taller San Cayetano",
        "cuenta_clearing_cvu": "0000003100094182901412",
        "tipo": "taller_gestor"
      },
      "alta_oficio": null
    }
  ],
  "especificacion_tecnica": {
    "articulo": "Art. 410-TX - Borcego Aconcagua Pro",
    "cantidad_pares": 500,
    "curva_talles": [
      {"talle": 38, "cantidad": 20},
      {"talle": 39, "cantidad": 40},
      {"talle": 40, "cantidad": 80},
      {"talle": 41, "cantidad": 120},
      {"talle": 42, "cantidad": 140},
      {"talle": 43, "cantidad": 70},
      {"talle": 44, "cantidad": 30}
    ],
    "merkle_root_bom": "0x7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d"
  }
}
```

#### 3. Política de Costos Congelados (Snapshots Inmutables vs Properties Dinámicas)
Para asegurar la estabilidad del crédito fiduciario y la trazabilidad industrial frente a la inflación:

1. **El Riesgo de las Properties Dinámicas:** Si los costos de la orden se calcularan exclusivamente mediante `@property` leyendo `ProductoTemplate.costo`, cualquier actualización posterior de precios en el catálogo alteraría retroactivamente el balance histórico de una OP ya confirmada o finalizada.
2. **Momento del Congelamiento (Trigger de Confirmación):**
   - Al pasar la orden de `borrador` a `confirmado` (o emitirse la e-OP), el sistema calcula el Vector C y los costos unitarios y los **persiste como snapshots inmutables** en campos `models.DecimalField` en la base de datos (`costo_mod`, `costo_cs`, `costo_bom`, etc.).
   - A partir de ese milisegundo, los valores quedan congelados y no vuelven a recalcularse dinámicamente.
3. **Indexación en UCI:** Para mitigar la pérdida de poder adquisitivo del tallerista y la descapitalización del FDI durante el plazo de ejecución (30 a 60 días), los costos congelados se expresan en **Unidades de Cuenta Industrial (UCI)**, referenciadas a la canasta sectorial INDEC/IPIM.
4. **Sellado Criptográfico:** Los valores congelados del Vector C forman parte del input determinista del payload canónico. Al calcular el `hash_seguridad` (SHA-256) y firmarlo con Ed25519, cualquier intento de alterar un costo congelado invalida la firma criptográfica en el Nodo MES y en el Portal Fiduciario del Banco.
5. **Desacople Arquitectónico:**
   - En `apps.produccion`: Se congela el costo fabril histórico (`costo_total_insumos_teorico` y los costos de servicios por etapa) para la valorización contable de inventario por partida doble.
   - En `apps.eop`: Se congela el Vector C fiduciario en UCIs para la garantía del Escrow y la liquidación del clearing ante el FDI.

### Portal Fiduciario (Dashboard de Clearing en la MES)

La liberación de fondos del Escrow no ocurre mágicamente; requiere que la entidad fiduciaria (FDI) y el Banco (agente de clearing) ejecuten la transferencia. La arquitectura lo resuelve construyendo un sub-módulo interno en el nodo de la MES:

1. **El Dashboard Fiduciario:** En `/mes/fiduciaria/` (o vía API), los oficiales de cuenta de la administradora del Fideicomiso acceden con el rol `FIDUCIARIO`.
2. **Bandeja de Entrada (Inbox) y Tablero de Fondeo:** Visualizan las e-OPs aprobadas por la Comisión de Crédito (o por Silencio Positivo) junto con el saldo disponible en la cuenta custodia del FDI.
3. **Generación de Lotes (El "Botón de Pago"):** Cuando autorizan, generan un "Lote de Liquidación" exportando un archivo batch estandarizado (`.txt` Interbanking/BAPRO Empresas) o disparando un Webhook corporativo hacia la API B2B del Banco.
4. **Endpoint de Retorno (Callback):** Tras el clearing exitoso del banco, Indinopy recibe la confirmación, dispara la Factura Electrónica de AFIP por el milisegundo exacto y cancela la posición de IVA diferido.

### Endpoints de Federación del Nodo MES (Pendiente de Desarrollar)

```python
# Registro de nodos en la red
POST /federacion/nodos/registrar/
GET  /federacion/nodos/lista/

# Registro de PTFs homologados
GET  /federacion/ptf/registro/               ← Lista pública de PTFs activos
GET  /federacion/ptf/{cuit}/certificado/     ← Certificado individual
POST /federacion/ptf/revocar/                ← Solo MES (autenticado)

# e-OPs y Escrow
POST /federacion/eop/entrante/               ← Recibe e-OP de nodo Comitente
POST /federacion/eop/{uuid}/firma/           ← Recibe firma de Tallerista o PTF
GET  /federacion/eop/{uuid}/estado/          ← Consulta estado Timelock

# Fideicomiso / Banco
GET  /federacion/banco/clearing/pendientes/  ← Lotes de pago a ejecutar
POST /federacion/banco/clearing/confirmar/   ← Webhook del BAPRO tras pagar
```

### Tarifario Homologado de Convenio y Nomenclador Sectorial (Vector C)

Para garantizar que el cálculo de la mano de obra façonera (Vector C de la e-OP) se actualice automáticamente sin acoplar la MES a los inventarios privados de cada marca, se utiliza el patrón de **Tarifario Homologado de Convenio y Mapeo Sectorial**:

1. **Catálogo Central (Nodo MES):** El nodo central mantiene el modelo `TarifaConvenio` utilizando un código universal (ej: `MES-SRV-APARADO-BOTA`). Define los precios de referencia de mano de obra en UCI homologados en paritarias, sin dependencias con `ProductoTemplate`.
2. **Mapeo Local (Nodo Marca):** En el ERP de cada marca (`apps.inventario`), el servicio interno (ej: "Aparado de Bota") tiene un campo `codigo_homologado_mes` donde el usuario enlaza su servicio local con la nomenclatura de la MES.
3. **Sincronización (Federación):** La MES distribuye las actualizaciones paritarias homologadas en el Boletín Oficial Sectorial y vía la API `/federacion/api/v1/tarifario/convenio/`.
4. **Snapshot Inmutable (Producción):** Al generar una e-OP, el motor busca el `codigo_homologado_mes`, extrae la tarifa de referencia y guarda los montos calculados en `costo_mod` y `costo_fdi` de la e-OP en Unidades de Cuenta Industrial (UCI). Si las tarifas paritarias cambian posteriormente, el contrato fiduciario de la e-OP ya firmada permanece inalterable.

---

## 6. Flujo del PTF (Promotor Territorial de Formalización)

### ¿Quién lo homologa?
La **ComisionCredito** del Distrito correspondiente. Es el cuerpo colegiado de 7 sillas (INTI, Sindicato, Talleristas Mono, Talleristas SAS, Marcas, Municipio, FDI) que vota la habilitación.

### Flujo de Registro de un PTF

```
1. PTF se postula ante la ComisionCredito de su municipio
2. Comisión vota habilitación (mayoría de las 7 sillas)
3. Si aprueba:
   a. PTF genera par de claves Ed25519 en su smartphone
      (clave privada NUNCA sale del Secure Enclave)
   b. PTF envía SOLO su clave pública a la MES
   c. MES crea PerfilPTF con zona de cobertura (MultiPolygonField)
   d. MES emite Certificado PTF firmado con MES_clave_privada
   e. MES distribuye el certificado a todos los nodos registrados
4. PTF instala app móvil y carga su certificado
5. Desde ese momento, sus firmas son verificables matemáticamente
   por cualquier nodo de la red, sin consultar a la MES en tiempo real
```

### Modelo `PerfilPTF` (Pendiente de Implementar)

```python
# En apps/mes/models.py
class PerfilPTF(TimeStampedModel):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    comision = models.ForeignKey(ComisionCredito, on_delete=models.RESTRICT)
    zona_cobertura = models.MultiPolygonField(srid=4326)  # PostGIS
    clave_publica_ed25519 = models.CharField(max_length=64)
    certificado_mes_json = models.JSONField()  # Certificado firmado por MES
    fecha_emision_credencial = models.DateField()
    fecha_vencimiento_credencial = models.DateField()
    activo = models.BooleanField(default=True)
    auditorias_realizadas = models.IntegerField(default=0)
    ucp_score_ptf = models.IntegerField(default=0)
```

---

## 7. Traslado Escalonado de Insumos a Producción

Para consultar la fundamentación teórica, doctrina legal (Arts. 1251 y 1356 CCCN) y mitigación de riesgo de apropiación indebida de materiales, ver:
> 🔗 [`docs/paper_protocolo_eop_gobernanza_industrial.html` (§4.2: Blindaje contra vectores de fraude en planta)](paper_protocolo_eop_gobernanza_industrial.html).

### Mecanismo Operativo en el Software
1. **Remitos de Traslado a Producción (`TRA-<OP>-EX`):** Los insumos no se despachan en bloque al inicio; se remiten de manera escalonada por etapa técnica (Corte $\to$ Aparado $\to$ Armado/Suelas).
2. **Topología de Doble Entrada:** El material enviado a talleres externos se traslada a ubicaciones de tipo `fason`. No se computa como salida definitiva ni venta; permanece en el activo de la empresa bajo custodia del tallerista con cláusula legal inyectada automáticamente.
3. **Techo de Rendimiento Estequiométrico (`Yield Cap`):** En `OPEtapaTracking`, el avance físico máximo declarable por el taller está restringido matemáticamente por el stock de materia prima efectivamente remitido al taller en custodia.
4. **Recepciones Físicas Parciales:** La fábrica emite remitos correlativos de ingreso (`ING-<OP>-PX`) controlando calidad (1ra, 2da, descarte) y devoluciones de sobrantes (`DEV-<OP>-XX`).

---

## 8. Roadmap de Implementación (Fases Pendientes)

### Fase 1 — Red Federada (Módulo MES)
- [x] **Tarifario Homologado de Convenio Federado**: Modelo `TarifaConvenio` con nomenclatura universal (ej: `MES-SRV-APARADO`) desacoplada y servicio `TarifarioConvenioService`.
- [x] **Boletín Oficial Sectorial**: Publicación consecutiva, sumario canónico firmado con Ed25519, reporte PDF institucional (`BoletinSectorialPDFReport`) y endpoint público federado.
- [x] Sincronización descentralizada de matriz de costos hacia nodos de Marcas vía endpoint público federado `/federacion/api/v1/tarifario/convenio/`.
- [x] Mapeo local de `ProductoTemplate.codigo_homologado_mes` en `apps.inventario` (Puente de cálculo).
- [x] Emisión, distribución y Lista de Revocación de Certificados (CRL) de credenciales PTF (`CRLService` y endpoint federado `/federacion/api/v1/pki/crl/`).
- [x] Worker Celery para Timelock de 48h (Silencio Positivo) en red (`procesar_silencio_positivo_timelock_async`).
- [x] Verificación GPS en `OPParteProduccion` (PoPW): Validación geoespacial en `ProduccionService.registrar_parte_produccion_popw` y en webhook federado contra `Contacto.ubicacion_catastral`.
- [x] **Portal Fiduciario & Clearing BAPRO**: `ClearingBAPROService` con generador de lotes batch estandarizados en texto plano (`.txt` Interbanking / BAPRO), Dashboard fiduciario MVT (`/mes/fiduciaria/`), endpoint de exportación `/federacion/api/v1/banco/clearing/pendientes/` y endpoint de callback y conciliación `/federacion/api/v1/banco/clearing/confirmar/`.
- [x] **Comunicaciones Oficiales y Cédulas Digitales Inter-Nodo**: Modelo `ComunicacionOficialFederada` (GDE sectorial), `ComunicacionOficialService` (emisión con firma Ed25519, acuses fehacientes de entrega y worker de notificación tácita a las 48h) y endpoints de buzón electrónico.
- [ ] **Permisos Institucionales**: Decoradores y validación de rol `OficialFiduciario` en vistas de clearing y restricción de firma Ed25519 en e-OP a apoderados legales y PTFs.

### Fase 2 — Integración Headless (API Gateway e-OP)
- [ ] Implementar flag `MODO_HEADLESS` en `ConfiguracionEmpresa` / `settings.py`
- [ ] Desacople de `ProduccionService`: Saltear `StockService` si es headless (inventario gestionado por SAP)
- [ ] Relajar restricción de `Receta` (BOM local) en `OrdenProduccion` usando `JSONField` (BOM dinámico externo)
- [ ] Endpoints DRF en `apps/produccion/` para recibir OPs crudas (`POST /api/v1/interna/e-op/`)
- [ ] Webhooks de retorno al ERP Legacy para informar liberación de hitos del Escrow

### Fase 3 — Consolidación de Producción Industrial, MRP y Portales de Taller (`apps.produccion`)

#### 1. Diagnóstico y Desacople
Con la extracción de la lógica fiduciaria a `apps.eop`, el módulo `apps.produccion` asume exclusivamente el rol de MRP y manufactura física de planta. Requiere finalizar la limpieza de campos y modelos residuales (`OPEscrowHito` en `models.py`, fieldsets fiduciarios en `admin.py` y lectura de `contrato_eop` en `api_views.py`).

#### 2. Checklist de Implementación
- [ ] **Desacople y Depuración Fiduciaria:**
  - [ ] Eliminar modelo residual `OPEscrowHito` de `apps/produccion/models.py`.
  - [ ] Limpiar fieldsets fiduciarios en `apps/produccion/admin.py` (`OrdenProduccionAdmin`).
  - [ ] Actualizar `RecepcionHeadlessEOPView` en `apps/produccion/api_views.py` para consultar `op.contrato_eop`.
- [ ] **Documentos y Reportes Industriales (`apps/produccion/reports/`):**
  - [ ] `OrdenProduccionPDFReport`: Hoja de Ruta de Planta (A4) con código QR de la OP, curva de talles desagregada por variación, BOM técnico y checklist de etapas.
  - [ ] `BOMExplosionReport`: Explosión de insumos y avíos por lote o tanda vs existencias en almacén.
  - [ ] `RendimientoProduccionExcelReport`: Matriz de desvíos y mermas comparando consumo teórico vs real (`cantidad_consumida_real`) con alerta INTI (>10%).
  - [ ] `LiquidacionFasonExcelReport`: Planilla de servicios prestados por talleres externos con discriminación de pares de 1ra y 2da selección.
- [ ] **Motor MRP y Planificación:**
  - [ ] Servicio de reabastecimiento automático: generación de OPs en borrador a partir de `OrdenVenta` confirmadas o quants por debajo del stock de seguridad.
  - [ ] Asignación de lote industrial (`lote_id`) y fecha de elaboración al ingresar producto terminado en `ProduccionService.finalizar_op()`.
- [ ] **Portales, Partes y Permisos Fabriles:**
  - [ ] Backend de validación territorial PoPW en `DeclararParteActionView`: comprobación de proximidad Point-in-Polygon entre `ubicacion_gps_declarada` y el catastro del taller (`contacto.ubicacion_catastral`).
  - [ ] Portal del Tallerista (PWA móvil) con WebAuthn/Passkeys, firma Ed25519 local y ficha técnica ciega de precios comerciales.
  - [ ] Segregación de visibilidad: implementar permiso `view_costos_op` para ocultar Vector C y márgenes a operarios, supervisores de pañol y talleristas externos.

### Fase 4 — Consolidación de Nómina, Régimen Previsional y Libro de Sueldos Digital (`apps.nomina`)

#### 1. Diagnóstico y Estado Actual
El módulo `apps.nomina` cuenta con la modelización básica de legajos (`Empleado`), convenios (`Sindicato`), licencias (`Licencia`), conceptos (`ConceptoLiquidacion`) y recibos (`LiquidacionNomina`). Ya contempla la reforma laboral de la Ley Bases (Fondo de Cese Laboral en reemplazo del Art. 245 CCCN) y el circuito SoD con aprobación dual de Tesorería (`aprobador_tesoreria`) que dispara automáticamente el asiento contable y la Orden de Pago.

#### 2. Checklist de Implementación
- [ ] **Documentos y Reportes Oficiales:**
  - [ ] Implementar `ReciboSueldoPDFReport` (`apps/nomina/reports/recibo_sueldo_report.py`) basado en `BasePDFReport`: diseño A4 de doble vía (Original Empresa / Duplicado Empleado), desagregando haberes remunerativos, conceptos no remunerativos, retenciones de ley, cargas patronales y espacio de firma hológrafa o digital.
  - [ ] Implementar `LibroSueldosDigitalTxtReport` (`apps/nomina/reports/lsd_report.py`) con los 4 registros de longitud fija requeridos por ARCA / AFIP:
    - Registro 1: Empleador y período liquidado.
    - Registro 2: Bases imponibles 1 a 10 de Seguridad Social y días tope.
    - Registro 3: Detalle de conceptos con código AFIP oficial.
    - Registro 4: Modalidad de contratación y pluriempleo.
  - [ ] Implementar `LiquidacionNominaExcelReport` (`apps/nomina/reports/liquidacion_excel_report.py`): Planilla mensual consolidada de haberes brutos, retenciones de empleados, netos de bolsillo y costo laboral total empresa (SIPA, Obra Social, ART, FNE, Fondo Cese).
  - [ ] Implementar `AcreditacionHaberesTxtReport` (`apps/nomina/reports/acreditacion_haberes_report.py`): Formato plano estándar de transferencias bancarias masivas a cuentas sueldo (Interbanking / Red Link / bancos comerciales).
- [ ] **Motor de Liquidación y Reglas Tributarias/Previsionales:**
  - [ ] Topes previsionales periódicos de ARCA/ANSES (Bases mínimas y máximas para cálculo de aportes SIPA/Ley 19032/Obra Social).
  - [ ] Algoritmo de retención de Impuesto a las Ganancias (4ta Categoría / Ingresos Personales) con deducciones SiRADIG (F. 572) y tabla progresiva acumulada.
  - [ ] Módulo de Novedades Variables mensuales: modelo o formulador dinámico para Horas Extras (50% y 100%), feriados trabajados y premios sin hardcode en servicios.
- [ ] **Integración Financiera, Datos Bancarios y SoD:**
  - [ ] Campos en `Empleado` para acreditación de haberes: `cbu_sueldo`, `banco` y `tipo_cuenta`.
  - [ ] Servicio de liquidación masiva de período: procesamiento en lote de toda la nómina activa del mes en un único clic, con previsualización y pase grupal a revisión de Tesorería.
  - [ ] Validación estricta SoD: verificación transaccional que impida que el usuario liquidador apruebe su propia nómina en tesorería (`usuario_preparador != aprobador_tesoreria`).

### Fase 5 — Frontend, UX y Portales (Fase Final de Cierre)
> **Estrategia de Desarrollo:** Esta fase se posterga al cierre del proyecto para garantizar que toda la maquinaria de backend, reglas de integridad criptográfica, motores de partida doble, servicios tributarios y flujos federados estén 100% estabilizados antes de construir las capas visuales.

- [ ] Template base (`base.html`) con sistema de diseño portado de los mockups HTML.
- [ ] Formularios dinámicos de alta de e-OP en Django.
- [ ] Dashboard de producción (OPs activas, stock, alertas).
- [ ] Panel de Escrow y Hitos para el Comitente.
- [ ] Panel del Tallerista (OPs asignadas, partes de producción).
- [ ] Portal web del PTF (`/mes/ptf/portal/`) con WebCrypto API para firmas en navegador.
- [ ] **Seed de Autorización**: Command `python manage.py setup_roles_permisos` para aprovisionamiento idempotente de Grupos Django, permisos y vistas por perfil.

---

## 9. Deuda Técnica Identificada

### Alta Prioridad
| Item | Archivo | Descripción | Estado |
|---|---|---|---|
| Refactor Payload Canónico (e-OP) | `apps/eop/models.py` | `generar_payload_canonico()` y `calcular_merkle_root_bom()` implementados en `ContratoEOP` con CUITs, vector de costos, total UCI, cronograma dinámico de hitos y etapas productivas. | ✅ Resuelto |
| Actualizar Serializador Federado | `apps/federacion/serializers.py` | `EntradaEOPSerializer` valida el array de hitos (`cronograma_escrow_hitos`), control de 100% de suma y firma Ed25519 sobre payload canónico. | ✅ Resuelto |
| Escrow Dinámico en Recepción e-OP | `apps/federacion/views.py` | `RecepcionEOPView.post` instancia dinámicamente los `EOPHitoEscrow` a partir del cronograma recibido en el payload (con fallback a 35/50% SBD). | ✅ Resuelto |
| Disparo de Webhook e-OP | `apps/federacion/services.py` | Implementado `FederacionCreditoService.transmitir_eop_a_mes()` con HTTP POST real del sobre de transporte hacia `/federacion/eop/entrante/`. | ✅ Resuelto |

### Media Prioridad
| Item | Descripción | Estado |
|---|---|---|
| Eliminar importaciones diferidas | En `federacion/views.py`, se centralizó `HttpResponseForbidden` al tope del archivo removiéndolo de todos los métodos `dispatch`. | ✅ Resuelto |
| Roles PTF en `MiembroComision` | Faltan los nodos: Talleristas Mono, Talleristas SAS, Municipio | Pendiente |
| Filtro por rol en OPListView | Cualquier usuario logueado ve todas las e-OPs | Pendiente |
| `Producto` sin `precio_venta` verificado | El campo en `ventas/services.py` puede no existir con ese nombre | Pendiente |
| `Contacto` sin campo `email` verificado | Usado en WooCommerce pero puede no estar en el modelo |

### Baja Prioridad (Mejoras)
- Paginación en todos los endpoints de la API de federación
- Rate limiting en el endpoint de Webhook
- Compresión de payloads canónicos para OPs con muchas variaciones
- Caché Redis para el registro de PTFs (evitar DB hits en cada verificación)

---

## 10. Referencias

- Protocolo e-OP y Mitigación de Fraude en Planta: `docs/paper_protocolo_eop_gobernanza_industrial.md` (§4.2)
- Dossier FIMCA Base y Sistema de Adelantos: `docs/dossier_fimca_base.md` (Sección II)
- Glosario de Conceptos Unificados del Proyecto: `docs/glosario_conceptos_proyecto.md`
- Flujos Documentales y Circuitos de e-OP: `docs/md/flujos_documentales.md`
- Documentación técnica del protocolo: `docs/explicacion_tecnica_proyecto.md`
- Arquitectura MES y Gobernanza: `docs/arquitectura_mes_gobernanza.md`
- WooCommerce REST API v3: https://woocommerce.github.io/woocommerce-rest-api-docs/

---

*Este documento es un plan vivo. Se actualiza a medida que avanza la implementación.*
