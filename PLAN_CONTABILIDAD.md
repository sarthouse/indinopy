# Plan de Implementación: Módulo de Contabilidad y Tributación Argentina
**Versión:** 1.0.0 | **Estado:** Aprobado para Desarrollo
**Contexto:** Ecosistema Indinopy (ERP/MES - RIGI Conurbano 2026)

Este documento detalla la arquitectura de la aplicación `apps.contabilidad`, diseñada a partir de la investigación cruzada entre un Arquitecto ERP y un Especialista Tributario para el cumplimiento normativo de ARCA (ex-AFIP) y agencias provinciales (ARBA/AGIP).

---

## 1. Visión y Principios Contables
El sistema operará bajo el principio de **Partida Doble Estricta**. Ningún movimiento económico puede quedar huérfano. Para cumplir con las reglas del protocolo RIGI, la contabilidad será el "Espejo Financiero" de los movimientos físicos y los eventos criptográficos.

---

## Estado Actual del Código (Diagnóstico)
Actualmente, el proyecto ya cuenta con una base parcial en `apps.contabilidad.models` que aloja:
*   `DocumentoDeuda` (Facturas) y `AplicacionPago` (Motor de Conciliación).
*   `Diario` (Puntos de Venta) e `Impuesto` (Tasas impositivas).
*   `CondicionPago` (Plazos y Cuotas).

**¿Qué falta construir según este nuevo plan?**
*   Toda la jerarquía base de Partida Doble (`Cuenta`, `Asiento`, `Apunte`).
*   Los modelos tributarios de retención y liquidación (`CertificadoRetencion`, `LiquidacionImpuesto`, `LiquidacionDetalle`).
*   El `ContabilidadService` para reemplazar la generación manual de deuda y automatizar la creación de Asientos enlazando las OP y Facturas mediante `GenericForeignKey`.

---

## 2. Arquitectura de Partida Doble (Modelos Base)
Se prescinde de los `Signals` mágicos de Django por ser propensos a errores y recursividad. Todo asiento será generado mediante el `ContabilidadService`.

### 2.1. El Plan de Cuentas (`Cuenta`)
Estructura jerárquica (árbol) donde solo las cuentas "hoja" (`imputable=True`) reciben apuntes.
*   **Campos clave:** `codigo` (ej: 1.1.01.001), `nombre`, `padre` (ForeignKey a self), `tipo` (Activo, Pasivo, PN, R+, R-), `naturaleza` (Deudora, Acreedora), `imputable` (Boolean).

### 2.2. El Libro Diario (`Asiento` y `Apunte`)
*   **Asiento:** Cabecera de la transacción. 
    *   Tiene un **Enlace Universal** (`content_type`, `object_id`) vía `GenericForeignKey` que lo une al documento que lo originó en `apps.documentos` (una Factura, una OP, un Recibo).
    *   *Regla de Negocio (Base de Datos):* Se prohíbe pasar el estado a `ASENTADO` si la suma total de `debe` no es exactamente igual al `haber` de sus apuntes.
*   **Apunte:** Las líneas del asiento. Una cuenta, un valor al `debe` y un valor al `haber`.

### 2.3. Libro Mayor y Balances
*   **Libro Mayor:** No será una tabla física. Será una Vista SQL / Consulta ORM que filtra los `Apuntes` por `cuenta` y calcula el acumulado usando `Window Functions`.
*   **Balance de Sumas y Saldos:** Un generador que agrupa apuntes por cuenta y resta el Debe/Haber según la naturaleza de cada una.

---

## 3. Tributación, ARCA y Gobernanza Fiscal

El esquema impositivo argentino exige separar la carga tributaria en diferentes instancias de tiempo (Facturación vs Pago).

### 3.1. Entidades de Configuración Maestra
*   **`Impuesto` y `RegimenImpositivo`:** Define las tasas impositivas (IVA 21%, Percepción IIBB ARBA, Retención Ganancias).
*   **`PerfilFiscal` (Asociado al Contacto):** Define si la PyME o el Tallerista es Responsable Inscripto, Monotributista o Sujeto Exento, y sus coeficientes de Convenio Multilateral (SIFERE).

### 3.2. Percepciones vs Retenciones (El Factor Tiempo)
El sistema divide las tablas operativas según cuándo ocurre el hecho imponible:
1. **Percepciones (Al Facturar):** Se crea el modelo `FacturaImpuesto`. Va atado a la Factura. Representa el recargo de IVA o IIBB que la PyME le cobra al cliente.
2. **Retenciones (Al Pagar):** Se crea el modelo `CertificadoRetencion`. Va atado a la Orden de Pago (Recibo/Payment), **no a la factura**. Se genera cuando nosotros pagamos de menos a un proveedor porque actuamos como agentes de retención (ej: Retención de Ganancias).

### 3.3. Liquidaciones y Pagos al Fisco (DDJJ)
*   **`LiquidacionImpuesto` (Cabecera):** Representa la Declaración Jurada mensual (ej. SICORE para ARCA).
*   **`LiquidacionDetalle`:** Tabla de control que une la Declaración Jurada con los `FacturaImpuesto` y `CertificadoRetencion` del mes, marcándolos como "Liquidados" para evitar doble imposición el mes siguiente.
*   **Anticipos y VEP:** El saldo final a pagar de esta liquidación generará automáticamente una *Cuenta por Pagar* a favor del fisco (ARCA), que luego se cancelará contra la cuenta bancaria mediante la generación del VEP en `tesoreria`.

---

## 4. Integración con el Módulo `documentos` y el Sistema Dual
El módulo `documentos` (que contiene las Facturas, Recibos y las e-OP) funciona como el disparador único (`Trigger`) de la contabilidad.

**Flujo de la e-OP (RIGI):**
1. La Marca firma la **e-OP** y fondea el Escrow en el FDI.
2. El `TesoreriaService` debita la cuenta Banco y el `ContabilidadService` genera un `Asiento` moviendo la plata de *Caja/Bancos* hacia una cuenta de Activo Transitorio: *Fondo Fiduciario Escrow*.
3. El Tallerista entrega la mercadería y el PTF firma la liberación del hito.
4. Se emite la **Factura M** (Liquidación de Fasón). 
5. El `FacturaService` genera el asiento de devengamiento (Gasto Producción a Proveedores).
6. Al mismo tiempo, el Fideicomiso liquida el pago al tallerista, saldando la deuda y efectuando (de forma invisible para el taller) las **Retenciones** correspondientes.

---

## 5. Roadmap de Implementación (Sub-Fases Contables)
1. Escribir archivo `models.py` de `apps.contabilidad` con Plan de Cuentas, Asiento y Apunte.
2. Armar Script de Importación Masiva (`importar_plan.py`) para CSVs.
3. Escribir modelos tributarios (`Impuesto`, `Retencion`, `Liquidacion`).
4. Conectar los `Servicios` de Facturación y Pagos para que escriban Asientos de forma automática (Sin signals).
5. Armar el generador de reportes en TXT para el aplicativo SICORE/SIFERE.
