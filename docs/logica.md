# Lógica de Negocio y Flujos

En Django, la lógica compleja se manejará en una capa de servicios (`services.py`) para orquestar la relación entre las Fichas Técnicas (Recetas) y la Producción.

## 1. Generación de OP a partir de una Receta (BOM)
La creación de una Orden de Producción (OP) no es manual campo por campo, sino un proceso de **instanciación**:

Cuando Ventas o Producción solicita fabricar "100 pares del Zapato X":
1. **Selección de Receta**: Se selecciona la `Receta` activa para ese producto.
2. **Cálculo de Insumos**: Un servicio recorre los `RecetaInsumo`. Multiplica la `cantidad_base` requerida de cuero, pegamento y suela por "100", generando automáticamente los registros de `OPInsumoRequerido`.
3. **Hoja de Ruta**: Se clonan los registros de `RecetaEtapa` hacia `OPEtapaTracking`, heredando las `observaciones_proceso` y el `tallerista_predeterminado` para esa etapa.
4. **Reserva de Herramientas**: Se bloquean las Hormas correspondientes en Almacén pasándolas a estado "En Uso".

## 2. Flujo Diferenciado de Ventas (Minorista vs Mayorista)
- **Minorista**: El pedido entra como pagado y se despacha de stock.
- **Distribuidor**: El pedido queda en "Esperando Seña". Al ingresar el pago en Tesorería, un signal de Django dispara el servicio mencionado en el punto 1 para generar la OP automáticamente basada en la receta.

## 3. Tracking de Producción y Liquidaciones
La OP es un proceso vivo:
- **Diferencia de Materiales**: Aunque la OP calculó 100 metros de cuero (según la receta), en el `OPInsumoRequerido` se puede anotar si realmente se consumieron 105 metros (merma).
- **Liquidación Automática**: Cuando el tallerista termina su etapa y se marca como "Finalizado" en el `OPEtapaTracking`, se genera una deuda a pagar en `tesoreria`.

## 4. Eventos Asíncronos (Celery)
- **Generación de PDF**: Conversión de `orden_produccion.html` a PDF en segundo plano.
- **Alertas de Quiebre de Stock**: Si al instanciar una OP a partir de una receta el inventario proyectado de un insumo cae bajo cero, enviar email a Compras.
