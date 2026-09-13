# Matriz de Roles, Permisos e Integración de Sistemas
Este documento detalla la estructura de permisos y segregación de funciones (SoD - Segregation of Duties) del ecosistema Indinopy, abarcando desde la capa de red federada hasta los permisos internos de los empleados de una PyME, y contempla los escenarios de integración con sistemas legacy (Modo Headless).

---

## 1. Roles a Nivel Infraestructura (La Red Federada)
Son los permisos asignados a los **Nodos (Servidores)** que interactúan en la PKI (Infraestructura de Clave Pública).

| Tipo de Nodo | Rol en la Red | Permisos y Capacidades |
| :--- | :--- | :--- |
| **Nodo MES (Gobernanza)** | Autoridad Certificante (CA) | Root de la red. Único con permisos para emitir/revocar certificados Ed25519 (PTFs, Nodos). Ejecuta Timelocks de 48h. Dispara Webhooks de clearing al Banco. |
| **Nodo Comitente** | Emisor de Contratos (PUSH) | Crea e-OPs. Consulta estado de hitos. **Bloqueo duro:** No puede auto-aprobarse hitos ni enviar órdenes de pago al FDI. |
| **Nodo Tallerista** | Receptor y Ejecutor | Recibe e-OPs entrantes. Emite firmas de Aceptación (inicio) y Solicitudes de Inspección (fin de lote). |
| **Nodo Fiduciario (Banco)** | Ejecutor de Clearing | Escucha en modo pasivo. Recibe particiones factoriales (98% taller, 2% MES) y devuelve `200 OK` de liquidación exitosa. |

---

## 2. Roles Organizacionales Internos (ERP Marca / Comitente)
Una marca estructurada requiere segregación de funciones para evitar fraudes internos y errores operativos. Indinopy cuenta con un sistema de perfiles (Groups de Django) detallado:

### A. Alta Gerencia y Legales
*   **Gerente General (CEO/Director):** Acceso de lectura global a todos los tableros de control (Finanzas, Producción, Ventas). No opera el día a día. Autoriza presupuestos macro.
*   **Apoderado Legal / Titular (Firma Criptográfica):** Es el **único** rol que posee la aplicación móvil (Secure Enclave) vinculada a la Clave Privada (Ed25519) de la empresa. Su única función operativa en el ERP es apretar el botón *"Firmar e-OP y Fondear Escrow"*. 

### B. Módulo de Producción y Suministros
*   **Jefe de Producción:** Modela las Recetas (BOM - Bill of Materials). Calcula los costos teóricos. Arma los lotes y deja las e-OPs en estado "Borrador". **No puede obligar financieramente a la empresa** (no tiene firma criptográfica).
*   **Jefe de Compras:** Accede al submódulo `apps.compras`. Recibe las alertas de quiebre de stock de insumos que dispara el Jefe de Producción. Emite Órdenes de Compra (OC) a proveedores de cuero/telas.
*   **Supervisor de Inventario / Pañol:** Solo accede a `apps.inventario`. Su rol es hacer los "Ingresos" (recepción de compras) y "Egresos" (armar los remitos de Maquila físicos para enviar al taller).

### C. Módulo Comercial
*   **Jefe de Ventas:** Administra la integración con WooCommerce (`apps.ventas`). Define políticas de precios, cupones y catálogos.
*   **Vendedor (Mostrador/Mayorista):** Perfil ultra-limitado. Solo puede generar "Órdenes de Venta" (Pedidos), ver el stock disponible en tiempo real y cargar remitos de despacho. No ve los costos de producción ni las e-OPs.

### D. Módulo Administrativo Financiero
*   **Tesorero / Jefe de Finanzas:** Opera `apps.tesoreria`. Paga el flujo Privado (Comprobantes X / Cuentas por Pagar) de forma manual. Audita los débitos automáticos del Escrow.
*   **Analista Contable:** Opera `apps.contabilidad`. Su única función es la conciliación bancaria y revisar que las Facturas Electrónicas de AFIP se hayan generado correctamente para enviar al estudio contable externo.

---

## 3. Roles Organizacionales (Módulo Taller / SAS)
*   **Titular del Taller:** Posee la llave privada para aceptar la e-OP. Es el responsable fiscal ante la MES y ARCA.
*   **Supervisor de Planta:** Opera la tablet de la fábrica. Hace click en los hitos diarios del "Flujo Privado" (*"Aparado Lote A terminado"*). No requiere conocimientos fiscales ni firmas.
*   **Operario / Destajista:** En talleres grandes, los operarios pueden tener un login básico donde solo escanean un código de barras para marcar su presentismo o la cantidad de pares cosidos, alimentando la métrica del Supervisor.

---

## 4. Roles Institucionales (Gobernanza / MES)
*   **Promotor Territorial (PTF):** Auditor de campo. App móvil restringida. Solo escanea QR, valida coordenadas GPS y emite la firma "Hito Correcto" o "Fallo".
*   **Miembro de Comisión de Crédito (Mesa):** Oficial del Nodo MES. Vota aprobaciones manuales, vetos o exclusiones en el panel de Gobernanza.
*   **Árbitro Jurisdiccional (Municipio/INTI):** Rol de juez. Puede congelar una cuenta Escrow si se eleva una Alerta Sindical (mediante el submódulo de mediación).

---

## 5. Implementación Modular: El Escenario "Headless" (API Gateway)

**¿Qué pasa si una empresa estructurada ya utiliza SAP, Odoo, Tango o Microsoft Dynamics para su contabilidad y ventas, y solo quiere usar Indinopy para el RIGI y las e-OPs?**

Indinopy está diseñado arquitectónicamente para funcionar en **Modo Headless (Gateway Criptográfico)**.

1. **Desactivación de Módulos Locales:** Mediante las variables de entorno (`NODE_ROLE`), la empresa desactiva `ventas`, `compras`, y `contabilidad` en su nodo Indinopy.
2. **El ERP Principal como Maestro:** SAP o Tango siguen manejando el catálogo de clientes, la facturación a AFIP y el stock.
3. **Comunicación API-to-API:** Cuando en SAP el Jefe de Producción crea una "Orden de Fabricación" que se va a tercerizar, SAP dispara un Webhook interno hacia la API de Indinopy.
4. **Indinopy como Firma y Escrow:** Indinopy recibe la orden, la formatea en el estándar e-OP, pide la validación biométrica del Apoderado Legal en su celular, hashea el documento y se encarga exclusivamente de rutearlo hacia la MES y bloquear los fondos en el Escrow.
5. **Retorno al Legacy:** Cuando la MES o el PTF aprueban el hito y el Banco gira la plata, Indinopy devuelve un Webhook a SAP avisando: *"El lote 123 está terminado y pagado, ya podés dar ingreso al stock físico en tu sistema"*.

Esta flexibilidad garantiza que la adopción del FIMCA 2026 no implique la traumática migración de sistemas legacy ("vendor lock-in") para empresas que ya invirtieron años en su software contable privado.
