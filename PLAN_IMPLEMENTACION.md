# Plan de Implementación — Indinopy ERP/MES
**Versión:** 0.2.0 | **Fecha:** Septiembre 2026  
**Autor:** Gabriel Sarthou  

---

## Índice

1. [Visión del Proyecto](#1-visión-del-proyecto)
2. [Arquitectura del Sistema](#2-arquitectura-del-sistema)
3. [Estado Actual del Código](#3-estado-actual-del-código)
4. [Primitivas Criptográficas](#4-primitivas-criptográficas)
5. [Red Federada y Flujo de e-OP](#5-red-federada-y-flujo-de-e-op)
6. [Flujo del PTF (Promotor Territorial de Formalización)](#6-flujo-del-ptf-promotor-territorial-de-formalización)
7. [Integración WooCommerce Multitienda](#7-integración-woocommerce-multitienda)
8. [Roadmap de Implementación](#8-roadmap-de-implementación)
9. [Deuda Técnica Identificada](#9-deuda-técnica-identificada)

---

## 1. Visión del Proyecto

Indinopy es un **ERP/MES para PyMEs de la industria del calzado y la indumentaria argentina**, construido sobre el protocolo de **Órdenes de Producción Electrónicas (e-OP)** que funcionan como **activos fiduciarios negociables**.

### Principios Fundamentales

- **La e-OP es inmutable.** Una vez confirmada y sellada con su hash criptográfico, sus términos económicos no pueden modificarse unilateralmente.
- **El Escrow es la garantía.** Los fondos del Comitente (Marca) quedan bloqueados en una cuenta de custodia digital hasta que el PTF libera el hito correspondiente.
- **La confianza es matemática, no institucional.** El sistema no confía en la palabra de ningún actor. Confía en firmas Ed25519 verificables y hashes SHA-256 deterministas.
- **El Silencio es Positivo.** Si en 48 horas ningún miembro de la MES vetó una e-OP, el sistema la aprueba automáticamente sin intervención humana (Timelock).

### Actores del Sistema

| Actor | Rol | Nodo |
|---|---|---|
| **Comitente (Marca)** | Genera la e-OP, fondea el Escrow | ERP propio (Indinopy) |
| **Tallerista** | Ejecuta la producción, firma aceptación | ERP propio (Indinopy) |
| **PTF** (Promotor Territorial de Formalización) | Auditor de campo, firma la liberación del Escrow | App móvil + Nodo MES |
| **Mesa de Enlace Sectorial (MES)** | Gobernanza, homologa PTFs, administra Timelock | Nodo central compartido |
| **Fiduciaria (FDI)** | Administra el fondo de garantía | Integración externa |

---

## 2. Arquitectura del Sistema

### Stack Tecnológico

```
Backend:        Django 6.1 (MVT + REST API)
Base de Datos:  PostgreSQL + PostGIS (coordenadas GPS)
ORM History:    django-simple-history (auditoría inmutable)
Criptografía:   hashlib (SHA-256) + PyNaCl (Ed25519)
Geoespacial:    django.contrib.gis (PointField, MultiPolygonField)
Facturación:    afip-py (WSFE/WSFEX)
E-Commerce:     WooCommerce REST API v3 (Webhooks + Polling)
Async / Tareas: Celery + Redis (Timelock 48h y encolamiento de Webhooks masivos)
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
| `base` | Mixins criptográficos, ConfiguracionEmpresa | — |
| `contactos` | Directorio de Clientes, Proveedores, Talleristas | — |
| `inventario` | Stock en tiempo real (Quants, doble entrada) | `StockService` |
| `produccion` | e-OP, BOM, Recetas, Etapas MES | `ProduccionService` |
| `tesoreria` | Escrow Digital, Cajas, Comprobantes | `EscrowService`, `TesoreriaService` |
| `compras` | Órdenes de Compra, Recepciones | `ComprasService` |
| `ventas` | Órdenes de Venta, WooCommerce | `VentasService` |
| `contabilidad` | Facturas AFIP, Conciliación | `FacturadorAFIP` |
| `mes` | Gobernanza MES, RegistroEOP, PTF, Timelock | [pendiente] |

---

## 3. Estado Actual del Código

### ✅ Implementado

#### Modelos Core
- `OrdenProduccion` con `DocumentoFirmableMixin` (UUID, hash, firmas JSON)
- `calcular_merkle_root_bom()` — Árbol de Merkle del BOM
- `generar_payload_canonico()` — Serialización determinista para hashing
- `sellar_hash_seguridad()` — Fijación irreversible del hash al confirmar
- `verificar_integridad_hash()` — Detección de manipulaciones post-sellado
- `StockQuant` — Foto en tiempo real del stock (partida doble)
- `MovimientoStock` + `LineaMovimientoStock` — Motor de doble entrada
- `ContratoEscrow` + `HitoEscrow` — Contrato de custodia digital
- `PerfilCriptografico` — Identidad Ed25519 de cada usuario del sistema
- `Contacto` con `ubicacion_catastral` (GPS), `es_taller_homologado`, `ucp_score`, `clave_publica_ed25519`
- `RegistroEOP` — Copia canónica en el nodo MES con Timelock

#### Gobernanza y Criptografía (Módulo MES)
- `ComisionCredito`, `PerfilPTF`, `ResolucionOP`, `TribunalArbitraje` — Modelos de gobernanza.
- `PTFService` — Motor criptográfico de validación Ed25519 (`PyNaCl`), verificación de firmas en campo y certificados canónicos.
- `PTFService` — Control espacial Point-in-Polygon (PostGIS) de zonas de cobertura.
- `PTFService` — Lógica de aprobación exprés, veto de e-OPs y Silencio Positivo (Timelock 48h).

#### Capa de Servicios
- `StockService.reservar_linea()` / `realizar_linea()` / `cancelar_linea()`
- `ProduccionService.confirmar_op()` / `finalizar_op()` / `cancelar_op()`
- `EscrowService.fondear_escrow()` / `liberar_hito()`
- `ComprasService.confirmar_oc()` / `cancelar_oc()`
- `VentasService.procesar_orden_woocommerce()` / `procesar_producto_woocommerce()`

#### Vistas (CBVs)
- Pattern ListViews + DetailViews en todos los módulos
- Pattern Action Views (POST-only) para todas las transacciones críticas
- Enrutamiento completo en `core/urls.py`

#### Integración WooCommerce
- `TiendaWooCommerce` — Modelo multitienda con credenciales por instancia
- `WooCommerceWebhookView` — Endpoint con validación HMAC-SHA256
- `WooCommerceAPIClient` — Cliente REST activo para polling fallback
- Mapeo completo de `line_items`, `fee_lines`, `shipping_lines`, `coupon_lines`, `meta_data`

#### Facturación AFIP
- `FacturadorAFIP` — Adapter para afip-py (WSFE)
- Soporte para IVA discriminado por línea
- Lee entorno (homologación/producción) desde `ConfiguracionEmpresa`

---

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

> **Pendiente crítico:** La verificación matemática Ed25519 (`PyNaCl`) no está implementada. Actualmente se verifica la presencia de `firma_hex` pero no su validez criptográfica.

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

El software elimina la barrera burocrática del tallerista informal (que carece de CUIT o Clave Fiscal). 
1. **Trigger de Alta:** Cuando un Tallerista acepta su primera e-OP desde la app, si su DNI no está registrado fiscalmente en la MES, el ERP genera un payload especial tipo `ALTA_OFICIO`.
2. **APIs RENAPER/ARCA:** El Nodo MES recibe el payload, valida la biometría del Tallerista vía API del RENAPER, y dispara un webservice hacia ARCA/AFIP para generar el alta en el **Monotributo Productivo** de forma 100% programática.
3. **Apertura de Cuenta Inembargable:** En el mismo milisegundo, vía Open Banking, se abre la **Cuenta de Clearing Técnica en el Banco Provincia**. Esta cuenta (tanto para el trabajador individual como para el taller gestor SAS) nace con el flag de **inembargabilidad** absoluta por ley, protegiendo los fondos de cualquier pasivo de la etapa informal previa.

### Portal Fiduciario y Operatoria Bancaria (BAPRO/FDI)

La liberación de fondos del Escrow no ocurre mágicamente; requiere que la entidad financiera (ej: Banco Provincia) ejecute el clearing. La arquitectura lo resuelve con el rol de **Fiduciario**:

1. **El Nodo MES tiene un Dashboard Bancario:** En `/mes/banco/` o vía API, el oficial de cuenta del Fideicomiso accede con rol `FIDUCIARIO`.
2. **Generación de Lotes (Batch TXT):** Cuando la MES aprueba 50 hitos en el día, el Fiduciario genera un "Lote de Liquidación" que exporta un archivo estandarizado (ej: formato Interbanking/BAPRO).
3. **API Directa (Open Banking):** Alternativamente, si el banco expone una API de pagos masivos corporativos, el worker de Celery (`EscrowService.liberar_hito`) puede inyectar la instrucción de pago B2B directamente al banco con la partición factorial (98% al CBU del taller, 2% al CBU de la MES).
4. **Comprobantes y Facturación:** Tras el clearing exitoso del banco, Indinopy llama al WSFE de AFIP, emite la Factura Electrónica y cancela la posición de IVA diferido.

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

### Oráculo de Precios y Nomenclador Sectorial (Vector C)

Para garantizar que el cálculo de la mano de obra y las cargas sociales (Vector C de la e-OP) se actualice automáticamente sin acoplar la MES a los inventarios privados de cada marca, se utilizará un patrón de **Nomenclador Sectorial (Mapping)**:

1. **Catálogo Abstracto (Nodo MES):** El nodo central mantiene un modelo `TarifaConvenio` utilizando un código universal (ej: `MES-SRV-APARADO-BOTA`). Define los costos base de mano de obra y los porcentajes de cargas sociales, sin dependencias con `ProductoTemplate`.
2. **Mapeo Local (Nodo Marca):** En el ERP de cada marca (`apps.inventario`), el servicio interno (ej: "Costura de mi Borcego") tiene un campo `codigo_homologado_mes` donde el usuario enlaza su servicio privado con la nomenclatura de la MES.
3. **Sincronización (Federación):** La MES dispara webhooks firmados criptográficamente cada vez que hay una actualización paritaria. Los nodos de las marcas reciben el JSON, validan la firma de la MES y actualizan su caché local de tarifas.
4. **Snapshot Inmutable (Producción):** Al crear una e-OP, el motor busca el `codigo_homologado_mes`, extrae la tarifa vigente del caché y guarda los montos calculados en `costo_mod` y `costo_cs` de la e-OP. Si las tarifas cambian al día siguiente, el contrato inteligente de la OP ya firmada permanece inalterable.

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
    zona_cobertura = models.MultiPolygonField(srid=4326)   # PostGIS
    clave_publica_ed25519 = models.CharField(max_length=64)
    certificado_mes_json = models.JSONField()              # Certificado firmado por MES
    fecha_emision_credencial = models.DateField()
    fecha_vencimiento_credencial = models.DateField()
    activo = models.BooleanField(default=True)
    auditorias_realizadas = models.IntegerField(default=0)
    ucp_score_ptf = models.IntegerField(default=0)
```

---

## 7. Integración WooCommerce Multitienda

### Arquitectura

Cada tienda WooCommerce es un `TiendaWooCommerce` vinculado a la `ConfiguracionEmpresa`. Las credenciales son por tienda (no globales).

### Flujo de Sincronización (Híbrido)

```
WEBHOOKS (Tiempo Real — Push)
  WooCommerce → POST /ventas/webhooks/woocommerce/{tienda_id}/
  ↓ Valida HMAC-SHA256 (X-WC-Webhook-Signature)
  ↓ Rutea por tópico (order.*, product.*, coupon.*)
  ↓ Delega a VentasService [ACK inmediato < 2 segundos]

POLLING API (Fallback — Pull)
  Celery Beat → cada 15 minutos
  WooCommerceAPIClient.sincronizar_ordenes_recientes()
  ↓ GET /wp-json/wc/v3/orders?after={ultima_sync}
  ↓ Compara date_modified_gmt para evitar sobreescrituras
  ↓ Delega al mismo VentasService (código DRY)
```

### Mapeo de Campos Críticos para Argentina

| Campo WooCommerce | Campo ERP | Nota |
|---|---|---|
| `meta_data._billing_cuit` | `Contacto.cuil` | Vital para AFIP |
| `meta_data._billing_condicion_iva` | `Contacto.condicion_iva` | Para Factura A/B/C |
| `meta_data._mercadopago_payment_id` | `OrdenVenta.transaccion_id` | Conciliación |
| `fee_lines[]` | `LineaRecargoOrden` | Recargo MercadoPago, etc. |
| `shipping_lines[0].method_id` | `OrdenVenta.metodo_envio_id` | Para remito |
| `coupon_lines[]` | `OrdenVenta.cupones_aplicados` | JSONField |

---

## 8. Roadmap de Implementación (Pendientes)

### Fase A — Frontend, UX y Portales (En curso)
- [ ] Template base (`base.html`) con sistema de diseño portado de los mockups HTML.
- [ ] Formularios dinámicos de alta de e-OP en Django.
- [ ] Dashboard de producción (OPs activas, stock, alertas).
- [ ] Panel de Escrow y Hitos para el Comitente.
- [ ] Panel del Tallerista (OPs asignadas, partes de producción).
- [ ] Portal web del PTF (`/mes/ptf/portal/`) con WebCrypto API para firmas en navegador.

### Fase B — Red Federada (Módulo MES)
- [ ] **Oráculo de Precios Federado**: Modelo `TarifaConvenio` con nomenclatura universal (ej: `MES-SRV-APARADO`) desacoplada.
- [ ] Sincronización descentralizada de matriz de costos hacia nodos de Marcas (Webhooks).
- [ ] Mapeo local de `ProductoTemplate.codigo_homologado_mes` en `apps.inventario` (Puente de cálculo).
- [ ] Endpoints de federación del Nodo MES (Receptor de e-OPs entrantes).
- [ ] Emisión, distribución y Lista de Revocación (CRL) de certificados PTF.
- [ ] Worker Celery para Timelock de 48h (Silencio Positivo) en red.
- [ ] Verificación GPS en `OPParteProduccion` (PoPW).

### Fase C — Integración Headless (API Gateway e-OP)
- [ ] Implementar flag `MODO_HEADLESS` en `ConfiguracionEmpresa` / `settings.py`
- [ ] Desacople de `ProduccionService`: Saltear `StockService` si es headless (inventario gestionado por SAP)
- [ ] Relajar restricción de `Receta` (BOM local) en `OrdenProduccion` usando `JSONField` (BOM dinámico externo)
- [ ] Endpoints DRF en `apps/produccion/` para recibir OPs crudas (`POST /api/v1/interna/e-op/`)
- [ ] Webhooks de retorno al ERP Legacy para informar liberación de hitos del Escrow

### Fase D — Gobernanza Institucional (COMPLETADA)
- [x] Completar `ComisionCredito` con las 7 sillas correctas
- [x] Flujo de votación polimórfico (Habilitación PTFs y Crédito)
- [x] Bolsa de Trabajo Productivo
- [x] Tribunal de Arbitraje (72h)
- [x] Alertas de Colusión (`AlertaColusion` con Celery)
- [x] Portal de Denuncias de la Comunidad Organizada (Addenda II)

### Fase E — Integración Fiscal Completa
- [ ] Implementación completa WSFE (Factura A, B, C)
- [ ] WSFEX (Facturas de Exportación)
- [ ] Factura de Crédito Electrónica (FCE / MiPyME)
- [ ] Liquidaciones de Fasón (Monotributo Productivo)
- [ ] Integración ARCA (ex-AFIP) para seguimiento tributario

### Fase F — App Móvil PTF (Fuera del scope Django)
- [ ] App Flutter/React Native
- [ ] Generación de par de claves en Secure Enclave del dispositivo
- [ ] Firma Ed25519 con desbloqueo biométrico (FaceID / Huella)
- [ ] Geolocalización y firma en campo
- [ ] Sincronización offline con el Nodo MES

---

## 9. Deuda Técnica Identificada

### Alta Prioridad
| Item | Archivo | Descripción |
|---|---|---|
| Refactor Payload Canónico (e-OP) | `produccion/models.py` | `generar_payload_canonico()` debe incluir CUITs, monto total UCI y el cronograma dinámico de etapas para acoplarse con la MES. |
| Actualizar Serializador Federado | `federacion/serializers.py` | `EntradaEOPSerializer` debe aceptar el array de hitos/etapas y sus porcentajes (`cronograma_pagos`) para armar el Escrow dinámico. |
| Escrow Dinámico en Recepción e-OP | `federacion/views.py` | `RecepcionEOPView.post` debe leer el array de etapas del payload (si existe) y generar los `HitoEscrow` proporcionalmente en lugar de hardcodear 2 hitos. |
| Disparo de Webhook e-OP | `produccion/services.py:178` | Reemplazar el `TODO` por la emisión HTTP real (POST vía `requests` o Celery) del payload canónico hacia la URL de la MES. |
| Verificación Ed25519 real | `tesoreria/services.py` | Hoy solo verifica que `firma_hex` existe, no que sea válida matemáticamente |
| Cancelación de stock en OV eliminada | `ventas/services.py:175` | `eliminar_orden_woocommerce` no llama a `StockService.cancelar_linea()` |
| `ConfirmarOVActionView` sin servicio | `ventas/views.py:33` | No llama a `VentasService.generar_remito_salida()` |
| Celery para Webhooks WooCommerce | `ventas/webhooks.py:46` | En producción el webhook sincrónico puede tardar >2s y ser desactivado |

### Media Prioridad
| Item | Descripción |
|---|---|
| Eliminar importaciones diferidas | En `federacion/views.py`, subir el `from django.http import HttpResponseForbidden` al tope del archivo para respetar la guía de estilo, sacándolo del interior de los métodos `dispatch`. |
| Roles PTF en `MiembroComision` | Faltan los nodos: Talleristas Mono, Talleristas SAS, Municipio |
| Filtro por rol en OPListView | Cualquier usuario logueado ve todas las e-OPs |
| `Producto` sin `precio_venta` verificado | El campo en `ventas/services.py` puede no existir con ese nombre |
| `Contacto` sin campo `email` verificado | Usado en WooCommerce pero puede no estar en el modelo |

### Baja Prioridad (Mejoras)
- Paginación en todos los endpoints de la API de federación
- Rate limiting en el endpoint de Webhook
- Compresión de payloads canónicos para OPs con muchas variaciones
- Caché Redis para el registro de PTFs (evitar DB hits en cada verificación)

---

## Referencias

- Documentación técnica del protocolo: `docs/explicacion_tecnica_proyecto.md`
- Arquitectura MES y Gobernanza: `docs/arquitectura_mes_gobernanza.md`
- Análisis y auditoría del código: `analisis_indinopy.md` *(en directorio de trabajo)*
- WooCommerce REST API v3: https://woocommerce.github.io/woocommerce-rest-api-docs/

---

*Este documento es un plan vivo. Se actualiza a medida que avanza la implementación.*
