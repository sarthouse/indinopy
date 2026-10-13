# Plan Técnico de Integración Fiduciaria con COELSA
**Fondo Fiduciario de Desarrollo Industrial (FDI) — Sistema Nacional de Pagos (BCRA)**

---

## 1. Contexto y Objetivo Institucional

Conforme al marco legal del **Fondo Fiduciario de Desarrollo Industrial (FDI)** y el régimen de contratos de manufactura fasonera (**Ley e-OP**), el FDI actúa como agente fiduciario de custodia y liquidación de garantías (*escrow*). 

Cuando un hito productivo es homologado y liberado por el Perito Técnico de Fasón (PTF) o expira el timelock de objeción sin controversias, los fondos en custodia deben transferirse de manera masiva, segura y trazable hacia las cuentas bancarias o de pago de los talleres confeccionistas.

En la República Argentina, el sistema central de compensación y liquidación electrónica multilateral es administrado por **COELSA (Cámara Compensadora Electrónica S.A.)**. 

Este documento establece los requerimientos funcionales, técnicos, normativos y de conectividad necesarios para coordinar con COELSA o la entidad financiera liquidadora del fideicomiso.

---

## 2. Modelos de Conectividad y Acceso

COELSA opera exclusivamente con entidades financieras y Proveedores de Servicios de Pago (PSP) participantes del Sistema Nacional de Pagos del BCRA. Existen dos vías arquitectónicas:

```
MODELO A (Indirecto - Vía Banco Fiduciario):
[FDI / fimca-core] ──(Host-to-Host / API)──► [Banco Liquidador] ──(Red COELSA)──► [Cuentas Talleristas]

MODELO B (Directo - PSP / Participante):
[FDI / fimca-core] ──(mTLS / SFTP Dedicado)──► [COELSA Directo] ──(SNP)──► [Cuentas Talleristas]
```

### Modelo A: Vía Banco Fiduciario Agente (Recomendado para inicio)
* **Descripción:** El FDI mantiene su cuenta especial recaudadora y de custodia en una entidad bancaria autorizada (Banco Fiduciario). El sistema del FDI genera los lotes de transferencia y los remite al banco mediante canales corporativos homologados (Interbanking, Host-to-Host o API bancaria corporativa). El banco inyecta las transferencias a COELSA.
* **Ventajas:** Menor carga regulatoria directa ante BCRA para el nodo del FDI; utiliza la infraestructura de liquidación ya operativa del banco fiduciario.

### Modelo B: Participante Directo / PSP
* **Descripción:** El FDI o su vehículo fiduciario tramita código de participante ante el BCRA y COELSA para liquidación directa de transferencias inmediatas (TI) o Débito Inmediato (DEBIN).
* **Ventajas:** Control absoluto sobre los ciclos horarios de compensación y conciliación intradía sin intermediación bancaria.

---

## 3. Requerimientos Técnicos a Solicitar a COELSA / Banco Liquidador

Para la integración formal del servicio `ClearingBancarioService` en `fimca-core`, se debe requerir la siguiente documentación y accesos técnicos:

### A. Especificación del Formato de Archivo Batch (Transferencias Masivas)
1. **Manual de Especificaciones Técnicas de Archivo (Diseño de Registro):**
   * Estructura estándar NACHA / ACH 150 adaptada por COELSA para transferencias en pesos (ARS).
   * Definición exacta de campos de:
     * **Cabecera de Lote (Header):** Código de entidad originante, número de lote, fecha/hora de presentación, identificador de aplicación.
     * **Registro de Detalle:**
       * CBU/CVU de origen (Cuenta FDI).
       * CBU/CVU de destino (22 dígitos del taller).
       * CUIT/CUIL del titular de destino (11 dígitos).
       * Importe en centavos (sin decimales explícitos, longitud fija de 15 dígitos).
       * Concepto de transferencia según normativa BCRA (ej. `FAC` - Facturas, `HON` - Honorarios de servicios).
       * Referencia alfanumérica unívoca (20 caracteres para el UUID o identificador de e-OP).
     * **Pie de Lote (Trailer):** Total de registros procesados, suma total de importes (campo hash de control).

### B. Servicio de Validación Previa de Padrón CBU / CVU / Alias
1. **API de Consulta en Tiempo Real (Padrón COELSA):**
   * Consumo previo al armado del lote para verificar:
     * Estado de la cuenta de destino (Activa / Bloqueada / Cerrada).
     * Correspondencia estricta entre CUIT declarado por el taller en su e-OP y la titularidad bancaria en COELSA (control anti-fraude y de identidad).
     * Tipo de cuenta (Bancaria tradicional CBU vs Billetera Virtual CVU).

### C. Especificación de Rendición y Códigos de Rechazo
1. **Archivo / Webhook de Devolución de Rendición:**
   * Archivo de retorno tras la ventana de compensación (Ciclos de Clearing).
   * Identificación de operaciones liquidadas exitosamente vs. rechazadas.
   * Tabla oficial de códigos de motivo de rechazo COELSA (ejemplos):
     * `R02`: Cuenta cerrada.
     * `R03`: CUIT no coincide con titular de la cuenta.
     * `R04`: CBU/CVU inexistente.
     * `R08`: Orden de no pagar / Cautelar.
     * `R10`: Falta de fondos en cuenta originante.
     * `R16`: Inconsistencia en dígito verificador.

### D. Seguridad y Canal de Comunicación
1. **Canal de Transporte:**
   * Conexión segura mediante túnel **VPN IPsec** dedicado o canal **SFTP Host-to-Host**.
   * Opcional API REST con autenticación mutua **mTLS (Mutual TLS)** con certificados X.509 homologados.
2. **Criptografía de Archivo:**
   * Firma digital y cifrado de los lotes mediante claves asimétricas PGP / GPG antes de la subida al servidor de COELSA o del banco.

---

## 4. Arquitectura de Impacto en el Sistema (`fimca-core`)

En el repositorio central `fimca-core`, el módulo de clearing se estructura en:

| Componente | Archivo | Responsabilidad |
| :--- | :--- | :--- |
| **Servicio de Liquidación** | [`fimca-core/fdi/services.py`](file:///home/tiago/programacion/indinopy/fimca-core/fdi/services.py) -> `ClearingBancarioService` | Compila los hitos en estado `liberado` y genera el payload/archivo estandarizado. Procesa el callback de confirmación. |
| **Modelo Fiduciario** | [`fimca-core/base/models.py`](file:///home/tiago/programacion/indinopy/fimca-core/base/models.py) -> `EOPHitoEscrow` | Almacena el `comprobante_pago` oficial de la liquidación bancaria y el estado del hito. |
| **Endpoints y Callbacks** | [`fimca-core/federacion/views.py`](file:///home/tiago/programacion/indinopy/fimca-core/federacion/views.py) -> `ClearingBatchAPIView` / `ClearingCallbackAPIView` | Descarga de lotes autorizados e ingesta de rendiciones del banco liquidador. |
| **Notificación Federada** | [`fimca-core/fdi/services.py`](file:///home/tiago/programacion/indinopy/fimca-core/fdi/services.py) -> `FederacionService` | Envío asíncrono del evento `clearing_hito_liquidado` hacia los nodos de la Marca y del Taller. |

---

## 5. Matriz de Preguntas Clave para la Mesa de Enlace con COELSA

Al iniciar el contacto técnico y comercial con COELSA o la mesa de banca fiduciaria, se deben plantear los siguientes puntos:

1. **Modalidad de homologación:** ¿Existe un entorno de Sandbox / Testing (Homologación) para enviar lotes de prueba y simular retornos con códigos de rechazo?
2. **Ciclos de compensación:** ¿Cuáles son las ventanas horarias de corte (*cut-off*) para transferencias inmediatas vs. compensación por lotes diferida (T+0 vs T+1)?
3. **Formatos soportados:** ¿Se requiere formato de texto plano de longitud fija (tipo COELSA 150) o admiten mensajería XML / ISO 20022 (pacs.008 / pain.001)?
4. **Validación de CBU/CVU por API:** ¿La consulta del padrón de CBU/CVU está disponible vía API REST sincrónica en tiempo real previa a la remisión del lote?
5. **Certificación de claves:** ¿Qué entidad certificante (CA) argentina debe emitir los certificados digitales para el sellado y firma de los archivos de transferencia?
