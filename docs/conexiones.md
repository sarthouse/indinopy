# Conexiones e Integraciones (WooCommerce)

Aunque usamos Django SSR para el frontend interno, el sistema necesita conectarse a plataformas externas.

## 1. Integración con WooCommerce

### A. Sincronización Pasiva (De WooCommerce a Django)
Implementaremos endpoints en Django para recibir **Webhooks**. Aunque no usemos FastAPI, podemos usar `Django REST Framework (DRF)` o simples vistas de Django que acepten `POST`.
- `POST /webhooks/woo/order-created/`
- La vista verifica la firma HMAC-SHA256 del payload.
- Inicia el flujo de Ventas (Validando si es Minorista y bajando stock, o si requiere OP).

### B. Sincronización Activa (De Django a WooCommerce)
- Cuando el módulo de `inventario` actualiza el stock de un Producto Terminado (`StockQuant`), Django envía una petición HTTP (usando la librería oficial `woocommerce`) para actualizar el stock en la tienda online.
- Para no penalizar la carga de la página del administrador, estas llamadas salientes se realizan mediante **tareas en segundo plano usando Celery y Redis**.

## 2. Facturación Electrónica (AFIP WSFE)
- Conexión vía certificados digitales (CRT y KEY) con los web services de AFIP para autorizar facturas electrónicas (obtención de CAE).
- Asociación directa con los datos fiscales de `contactos.Contacto` (CUIT/CUIL y condición frente al IVA).

## 3. API Interna (Opcional)
Si a futuro los talleristas necesitan una app móvil para escanear QRs y avanzar etapas de la OP, se expondrán endpoints de solo-lectura/actualización usando Django REST Framework.
