# ADR-004 · Seguimiento del pedido por polling cada 20 s

- **Estado:** Aceptado
- **Fecha:** 2026-11-24
- **Autor:** Juan

## Contexto

Después de pedir, el cliente quiere saber **cuándo está listo su pedido** para salir hacia la tienda. El estado cambia pocas veces (Confirmado → En preparación → Listo para recoger → Entregado) a lo largo de 30–90 minutos. El cliente **no tiene cuenta** (no hay a quién enviarle notificaciones push autenticadas) y el email es opcional.

## Alternativas

| | API WebSocket (API Gateway) | Notificaciones por email (SES) | **Polling cada 20 s** |
|---|---|---|---|
| Latencia del aviso | Inmediata | Segundos a minutos (y depende de que el cliente mire el correo) | Hasta 20 s |
| Infraestructura adicional | API WebSocket, tabla de conexiones, Lambdas de `$connect`/`$disconnect`, envío desde `admin-orders` | SES (verificar dominio, salir del *sandbox*), plantillas | **Ninguna**: reutiliza `GET /api/orders/{id}` |
| Costo | Mensajes + minutos de conexión + escrituras de conexiones | Por correo enviado | ~30 consultas por pedido × 2.760 pedidos/mes ≈ 83.000 invocaciones/mes (centavos) |
| Funciona sin email | Sí | **No** (el email es opcional) | Sí |
| Complejidad y riesgo | Alta (reconexiones, conexiones huérfanas, estado distribuido) | Media (entregabilidad, spam, datos personales en correos) | Baja |

## Decisión

`pedido.html` consulta `GET /api/orders/{orderId}?code=…` **cada `pollIntervalMs` (20 s)**, con tres reglas que acotan el costo:

1. **Se pausa** cuando la pestaña está oculta (`visibilitychange`) y consulta de inmediato al volver.
2. **Se detiene** al llegar a un estado final (Entregado, Cancelado, No recogido).
3. Un botón **"Actualizar ahora"** permite consultar sin esperar.

El intervalo vive en `config.js` y se puede ajustar sin tocar código. Cuando el estado cambia, la página muestra un aviso en una región `aria-live` (accesible para lectores de pantalla).

## Consecuencias

**Positivas**

- **Cero infraestructura nueva**: la misma ruta y la misma Lambda que la consulta normal del pedido.
- **Costo acotado y predecible**: con pausa y parada, ~30 consultas por pedido en promedio; pasar de 5 s a 20 s reduce las llamadas unas 3–4 veces.
- **Sin estado de conexiones** que mantener ni limpiar; funciona igual en cualquier navegador y red.
- No requiere el email del cliente (menos datos personales).

**Negativas y cómo se mitigan**

- **Hasta 20 s de latencia** en enterarse de un cambio → irrelevante para recoger pan (los estados cambian cada varios minutos); el botón "Actualizar ahora" cubre al impaciente.
- **Peticiones "vacías"** (sin cambios) → acotadas por la pausa y la parada; el throttling de API Gateway protege frente a abusos.
- **Mejora futura**: API WebSocket o SES para avisar "Listo para recoger" sin que el cliente tenga la página abierta, si el volumen o la experiencia lo justifican.
