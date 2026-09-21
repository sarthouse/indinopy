# Flujos Documentales en Indinopy ERP/MES

Este documento detalla la estructura administrativa, los módulos operativos y los circuitos documentales del sistema **Indinopy ERP/MES**, garantizando la trazabilidad entre el abastecimiento de materias primas, la fabricación, la logística comercial y el devengamiento fiscal.

---

## 1. Módulos Operativos del Sistema

* **Compras (`apps.compras`):** Solicitudes de Cotización (RFQ), Órdenes de Compra a proveedores, seguimiento de tarifas y conciliación *3-Way Matching*.
* **Producción (`apps.produccion` y `apps.eop`):** Ciclo de vida de la Orden de Producción (gestión interna de planta o e-OP fiduciaria federada con la MES), recetas técnicas (BOM) y partes de avance físico (PoPW).
* **Inventario (`apps.inventario`):** Gestión de existencias por partida doble (`StockQuant`). Administra Remitos de Recepción, Remitos de Traslado a Producción (custodia en talleres/fasón) y Remitos de Entrega comercial.
* **Ventas (`apps.ventas` e `apps.integraciones`):** Presupuestos comerciales, Notas de Pedido, Órdenes de Venta mayoristas B2B y canal omnicanal desacoplado (WooCommerce, MercadoLibre).
* **Contabilidad y Fiscal (`apps.contabilidad` y `apps.afip`):** Libro Diario por partida doble, facturación electrónica A/B/C/X con QR oficial ARCA, cuentas corrientes y reportes de Convenio Multilateral (CM05/CM03).
* **Tesorería y Custodia (`apps.tesoreria`):** Gestión de cajas, clearing bancario, administración fiduciaria de Escrow y Títulos de Crédito FCE (Ley 27.440).

---

## 2. Documentos Centrales del Circuito

| Documento | Módulo Emisor | Función Operativa / Legal | Efecto en Inventario / Caja |
| :--- | :--- | :--- | :--- |
| **Solicitud de Cotización (RFQ)** | `compras` | Consulta de precios, plazos de entrega y validez a proveedores. | No vinculante. Sin efecto en stock ni deuda. |
| **Orden de Compra (PO)** | `compras` | Compromiso formal de compra de insumos/servicios. | Al confirmarse, genera remito de recepción en Almacén. |
| **Presupuesto / Cotización** | `ventas` | Propuesta económica estimada a prospectos o clientes. | No vinculante. **No reserva stock físico**. |
| **Nota de Pedido / OV** | `ventas` | Pedido formal de venta (B2B mayorista o e-commerce). | Al confirmarse, genera remito y **reserva stock en `StockQuant`**. |
| **Remito Traslado a Producción** | `inventario` | Envío de materias primas y semielaborados a taller/fasón. | Mueve stock a ubicación `fason` bajo custodia (Arts. 1251/1356 CCCN). |
| **Remito de Recepción** | `inventario` | Ingreso físico de materias primas o productos terminados. | Incrementa stock disponible y actualiza cantidades en OC/OP. |
| **Remito de Entrega** | `inventario` | Despacho logístico de mercadería al cliente final. | Descuenta existencias físicas y cancela reservas. |
| **e-OP (Orden Producción Electrónica)** | `produccion` / `eop` | Título de colateral fiduciario inmutable sellado (SHA-256 / Ed25519). | Compromete insumos y activa el contrato Escrow / Timelock 48h. |
| **Factura A / B / C / X** | `contabilidad` | Comprobante de devengamiento comercial y fiscal (CAE AFIP). | Registra derecho a cobro / deuda y crédito/débito fiscal IVA. |

---

## 3. Diagramas Secuenciales de Flujo

### A. Circuito de Compras y Abastecimiento (3-Way Matching)

```mermaid
sequenceDiagram
    participant P as Proveedor
    participant C as Compras (Indinopy)
    participant A as Almacén (Inventario)
    participant K as Contabilidad

    C->>P: Emite Solicitud de Cotización (RFQ PDF)
    P->>C: Cotiza precios y plazo de entrega
    C->>C: Confirma Orden de Compra (OC PDF)
    C->>A: Genera Remito de Recepción REC-OC... (Borrador)
    
    P->>A: Entrega física de insumos en fábrica
    A->>A: Control de bultos y validación (LMS realizado)
    A->>A: Finaliza remito: StockQuant pasa a Disponible
    A-->>C: Señal sincroniza cantidades recibidas en la OC
    
    P->>K: Envía Factura Comercial
    K->>C: ComprasService.crear_factura_proveedor()
    Note over C,K: 3-Way Match: Coteja OC vs Remito vs Factura
    K->>K: Emite DocumentoDeuda (Factura Proveedor)
    C->>C: Actualiza cantidad_facturada (Cierre de OC)
```

---

### B. Circuito de Producción y Custodia de Materiales

```mermaid
sequenceDiagram
    participant M as Marca (Planta Central)
    participant E as ERP Producción
    participant T as Taller / Fasón Externo
    participant F as FDI / Mesa de Enlace (MES)

    M->>E: Crea Orden de Producción (Receta BOM)
    E->>E: Confirmar OP: Reserva Lógica de Insumos RES-<OP>
    
    opt Modo Federado e-OP
        E->>F: Emite e-OP (Payload canónico + Firma Ed25519)
        F->>T: Desembolsa Hito Cero (35-40% Capital de Trabajo)
    end
    
    M->>T: Emite Remito de Traslado a Producción (TRA-<OP>-EX)
    Note over M,T: Stock pasa de Almacén Central a Ubicación Fasón<br/>(Inembargable según Arts. 1251 y 1356 CCCN)
    
    T->>E: Registra avance físico PoPW (Pares terminados + Mermas)
    
    T->>M: Entrega producto terminado (Remito de Recepción ING-<OP>)
    M->>M: Control de calidad (1ra, 2da selección)
    M->>M: Reingreso de stock a Almacén Principal y consumo de insumos
```

---

### C. Circuito de Ventas y Omnicanalidad

```mermaid
sequenceDiagram
    participant CL as Cliente (B2B o Web)
    participant V as Ventas (Indinopy)
    participant I as Inventario (StockService)
    participant K as Contabilidad / AFIP

    alt Cotización Comercial B2B
        CL->>V: Solicita presupuesto
        V->>CL: Emite Presupuesto PDF (Con validez en días)
        Note over V,I: No reserva stock físico
        CL->>V: Aprueba presupuesto
    else Canal E-Commerce (WooCommerce / MeLi)
        CL->>V: Compra online (Webhook HMAC-SHA256 encolado en Celery)
    end

    V->>V: Confirma Orden de Venta (OV)
    V->>I: VentasService.generar_remito_salida(OV)
    I->>I: Reserva stock en StockQuant (Disponible = Física - Reservada)
    
    I->>CL: Despacha mercadería con Remito de Entrega (REM-OV)
    I->>I: Realiza remito: Descuenta stock físico y cancela reserva
    
    V->>K: VentasService.generar_factura_desde_orden(OV)
    K->>K: Solicita CAE en ARCA/AFIP (Factura A/B/C) con QR oficial
```

---

## 4. Reglas de Integridad del Sistema

1. **Partida Doble Estricta:**
   - En **Inventario**, ningún insumo o producto se crea o destruye: todo movimiento exige una ubicación origen y una ubicación destino.
   - En **Contabilidad**, ningún comprobante se asienta si la suma del Debe no es idéntica a la suma del Haber.
2. **Reserva vs Consumo:**
   - La confirmación de una orden (OV u OP) **reserva** existencias para evitar la sobreventa o el desabastecimiento; la baja física real solo ocurre al validar el remito correspondiente.
3. **Desacople Arquitectónico (Service Layer):**
   - Las transacciones documentales complejas se ejecutan exclusivamente en la capa de servicios (`ComprasService`, `ProduccionService`, `VentasService`, `StockService`), garantizando atomicidad transaccional (`@transaction.atomic`).
