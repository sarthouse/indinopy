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
* **Nómina y RRHH (`apps.nomina`):** Legajos de personal, novedades mensuales, liquidación de haberes, recibos de sueldo (Ley 20.744), exportación a Libro de Sueldos Digital (LSD ARCA) y segregación estricta SoD (`usuario_preparador != aprobador_tesoreria`).

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
| **Recibo de Sueldo (Ley 20.744)** | `nomina` | Comprobante legal de liquidación de haberes y aportes retenidos. | Sin efecto directo en stock. Devenga pasivo laboral y cargas sociales. |
| **Declaración F.931 / LSD** | `nomina` | Archivo de importación oficial ARCA (Libro de Sueldos Digital). | Genera la base de cálculo consolidada de aportes y contribuciones patronales. |
| **Orden de Pago (OP Tesorería)** | `tesoreria` | Mandato de egreso bancario/efectivo (proveedores, nómina, repago FDI). | Descuenta saldo en `CajaBanco` y cancela pasivos en `DocumentoDeuda`. |

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

### B. Circuito de Producción y Custodia de Materiales (Planta Propia o Fasón)

```mermaid
sequenceDiagram
    participant M as Marca Comitente (ERP)
    participant T as Tallerista (MES / Taller Propio)
    participant F as Fideicomiso FDI (Clearing BAPRO)
    participant K as Contabilidad & Tesorería Marca

    M->>M: Crea Orden de Producción (Receta BOM)
    M->>M: Confirmar OP: Reserva Lógica de Insumos RES-<OP>
    
    opt Modo Federado e-OP (Fasón Externo con Colateral)
        M->>F: Emite e-OP (Payload canónico sellado Ed25519)
        F->>T: Desembolsa Hito Cero (35-40% directo al Taller)
        M->>K: Asienta extinción deuda taller y registra Pasivo Fiduciario FDI
    end
    
    M->>T: Remito de Traslado a Producción (TRA-<OP>-EX)
    Note over M,T: Stock pasa de Almacén Central a Ubicación Fasón<br/>(Inembargable según Arts. 1251 y 1356 CCCN)
    
    T->>M: Registra avance PoPW (Pares terminados + Mermas)
    
    alt En Modo Federado e-OP
        F->>T: Desembolsa Hitos de Avance según certificación física
    end

    T->>M: Entrega producto terminado (Remito de Recepción ING-<OP>)
    M->>M: Control de calidad (1ra y 2da selección) y reingreso a Almacén
    
    opt En Modo Federado e-OP
        Note over M,K: A 60 días: Tesorería Marca cancela crédito fiduciario con OP repago
        K->>F: Orden de Pago con ComprobanteTesoreria(escrow_asociado)
    end
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

### D. Circuito de Nómina y Segregación de Funciones (SoD)

```mermaid
sequenceDiagram
    participant R as RRHH / Nómina (Preparador)
    participant T as Tesorería / Finanzas (Aprobador)
    participant K as Contabilidad General
    participant B as Banco / ARCA (LSD)

    R->>R: Carga de novedades (asistencias, horas extras, mermas)
    R->>R: Ejecuta preliquidación de haberes del período
    R->>R: Genera borrador: Recibos Ley 20.744 y exportación LSD ARCA
    R->>T: Envía liquidación a revisión (Estado: PENDIENTE_APROBACION)

    Note over R,T: Validación estricta SoD en Base de Datos:<br/>aprobador_tesoreria != usuario_preparador
    
    T->>T: Verifica totales remunerativos, retenciones y aportes
    T->>T: Confirma aprobación definitiva de la nómina
    
    T->>K: Genera asiento de sueldos y cargas sociales a pagar
    T->>B: Emite Orden de Pago masiva (acreditación bancaria)
    T->>B: Presenta archivo LSD en ARCA y genera VEP F.931
```

---

### E. Circuito de Tesorería Comercial y Cancelación Fiduciaria

```mermaid
sequenceDiagram
    participant D as Deuda Comercial / Fiduciaria
    participant T as Tesorero (Indinopy)
    participant B as Caja / Banco (Clearing)
    participant K as Libro Diario (Partida Doble)

    alt Pago a Proveedores o Liquidación Directa
        D->>T: DocumentoDeuda pendiente (Factura Proveedor / Sueldos)
        T->>B: Emite Orden de Pago (OP-PROV / OP-NOM)
        B->>B: Descuenta saldo en CajaBanco
        T->>K: Asiento: Debita Proveedores/Sueldos, Acredita Caja/Banco
    else Repago de e-OP Fiduciaria al FDI (A 60 días)
        D->>T: Vencimiento de Colateral Escrow (ContratoEOP)
        T->>B: Emite ComprobanteTesoreria con escrow_asociado
        B->>B: Transferencia clearing bancario al Fideicomiso FDI
        T->>K: Asiento: Debita Pasivo Fiduciario FDI, Acredita Banco
    end
```

---

## 4. Reglas de Integridad del Sistema

1. **Partida Doble Estricta:**
   - En **Inventario**, ningún insumo o producto se crea o destruye: todo movimiento exige una ubicación origen y una ubicación destino.
   - En **Contabilidad**, ningún comprobante se asienta si la suma del Debe no es idéntica a la suma del Haber.
2. **Reserva vs Consumo:**
   - La confirmación de una orden (OV u OP) **reserva** existencias para evitar la sobreventa o el desabastecimiento; la baja física real solo ocurre al validar el remito correspondiente.
3. **Segregación de Funciones (SoD):**
   - El operador que liquida haberes o confecciona facturas/órdenes de pago no puede autoaprobar el desembolso financiero (`usuario_preparador != aprobador_tesoreria`).
4. **Desacople Arquitectónico (Service Layer):**
   - Las transacciones documentales complejas se ejecutan exclusivamente en la capa de servicios (`ComprasService`, `ProduccionService`, `VentasService`, `StockService`, `NominaService`, `TesoreriaService`), garantizando atomicidad transaccional (`@transaction.atomic`).
