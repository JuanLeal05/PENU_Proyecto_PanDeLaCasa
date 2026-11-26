# 3. Arquitectura propuesta

## 3.1 Vista general

La solución es **100 % serverless y administrada**: no hay servidores, contenedores, VPC ni recursos que cobren por hora. Cada pieza escala con la demanda y cuesta casi cero cuando no hay tráfico (la panadería solo vende de 06:00 a 18:00).

![Arquitectura en AWS](../diagrams/png/02_arquitectura_aws.png)

*Figura 2. Arquitectura en AWS (`us-east-1`). Diagrama elaborado por Juan Pablo.*

## 3.2 Servicios por capa

| Capa | Servicio | Para qué | Por qué este (resumen; detalle en los ADR) |
|---|---|---|---|
| Presentación | **CloudFront + S3** (dos sitios: cliente en la raíz y panel en `/admin/`) | HTML/CSS/JS sin build, imágenes y `catalog.json` | Contenido estático cacheado en el borde, HTTPS, buckets privados con OAC. El tráfico más alto (catálogo e imágenes) nunca toca Lambda (ADR-003). |
| API | **API Gateway HTTP API** + JWT authorizer de Cognito | 14 rutas REST; las `/api/admin/*` exigen JWT | Más barato que REST API, JWT nativo, throttling por ruta, CORS sin invocar Lambda (ADR-005). |
| Cómputo | **AWS Lambda ×7** (Python 3.12, ARM64, 256 MB, 10 s) | Lógica de negocio; un handler por responsabilidad | Pago por invocación, escala solo, sin parches (ADR-001). |
| Datos | **DynamoDB ×4** (on-demand) + **S3** (assets) | `products`, `orders` (+ GSI `byDate`), `slots`, `idempotency`; fotos y catálogo | Transacciones condicionales para cupo y stock, $0 en reposo, multi-AZ, PITR (ADR-002). |
| Identidad | **Cognito** (Hosted UI, PKCE) + **IAM** | Login del personal; un rol por Lambda | Sin gestionar contraseñas; mínimo privilegio. |
| Integración y jobs | **EventBridge Scheduler** | `reset_stock` 05:30 y `close_day` 18:30 (zona `America/Bogota`) | Cron administrado con zona horaria, sin servidor. |
| Operación | **CloudWatch** (logs, métricas EMF, dashboard, alarmas) + **SNS** + **Budgets** | Observabilidad y control de costo | Integrado con Lambda; las métricas de negocio salen de los logs sin llamadas extra. |
| Entrega | **Terraform** + **GitHub Actions** (OIDC) | Infraestructura como código y CI/CD `dev` → `prod` con aprobación | Reproducible, revisable en PR, sin llaves de AWS en GitHub (ADR-006, ADR-007). |

### Las 7 funciones Lambda

Todas comparten el mismo paquete (la carpeta `backend/src`, sin dependencias externas: `boto3` viene en el runtime) y cambian solo el handler.

| Función | Rutas / disparador | Responsabilidad |
|---|---|---|
| `public-availability` | `GET /api/health`, `GET /api/availability` | Salud (smoke test) y cupos + stock de hoy |
| `create-order` | `POST /api/orders` | Validar, aplicar reglas y crear el pedido en **una transacción** con idempotencia |
| `order-status` | `GET /api/orders/{id}`, `POST /api/orders/{id}/cancel` | Consulta con código y cancelación por el cliente |
| `admin-orders` | `GET /api/admin/orders`, `PATCH .../status` | Pedidos del día y cambios de estado |
| `admin-products` | CRUD de productos, foto (URL prefirmada), inventario | Gestión del catálogo; regenera `catalog.json` |
| `admin-stats` | `GET /api/admin/stats` | Agregados del día |
| `scheduled-jobs` | EventBridge Scheduler | `reset_stock` y `close_day` |

Separar por responsabilidad permite **un rol IAM por función** con solo lo que necesita (por ejemplo, `admin-stats` solo puede hacer `Query` sobre el índice de pedidos) y que un error o un pico en una ruta no afecte a las demás.

### Modelo de datos

| Tabla | Clave | Uso |
|---|---|---|
| `pdc-<env>-products` | `productId` | Catálogo, precio, `dailyProduction`, `stock`, `active` (~40 ítems) |
| `pdc-<env>-orders` | `orderId` · GSI `byDate` (`pickupDate`, `slotKey`) | Pedidos; el GSI lista los del día ordenados por franja y hora de creación |
| `pdc-<env>-slots` | `date` + `slot` | Contador de pedidos activos por franja (TTL de 7 días) |
| `pdc-<env>-idempotency` | `idempotencyKey` | Respuesta original de cada `POST /api/orders` (TTL de 24 h) |

## 3.3 Flujo de un pedido, paso a paso

1. **Catálogo (estático).** El navegador pide `/assets/catalog/catalog.json` a CloudFront (caché de 60 s) **en paralelo** con `GET /api/availability`. Nombres, precios y fotos salen del CDN; solo los cupos y el stock pasan por Lambda.
2. **Disponibilidad.** `public-availability` hace un `Query` a `slots` (franjas de hoy) y un `Scan` de productos activos (stock). Devuelve las 22 franjas con `remaining` y `available` (≥ 30 min de anticipación, cupo > 0 y tienda abierta).
3. **Carrito.** Vive en el navegador (`localStorage`), que hace cumplir los límites de 20 unidades y 10 productos. **El precio nunca se envía**: lo pone el backend.
4. **Envío con idempotencia.** Al confirmar, el front genera **una** `Idempotency-Key` (UUID v4) por intento de compra y la reutiliza si hay un error de red; el botón se deshabilita mientras la petición está en curso (anti doble clic).
5. **Validación y reglas.** `create-order` valida el cuerpo, revisa si la clave ya existe (si sí, devuelve **la misma respuesta** con 200), verifica horario y anticipación, y lee los productos (`BatchGetItem`) para tomar **precios de la base de datos**.
6. **Transacción.** Una sola `TransactWriteItems` (todo o nada, §3.6) reserva el cupo, descuenta el stock, inserta el pedido y guarda la clave de idempotencia. Si falla, se traduce a `SLOT_FULL`, `OUT_OF_STOCK` o a la respuesta del pedido ganador.
7. **Respuesta.** 201 con el pedido y el **código de 6 caracteres** (única respuesta pública que lo incluye). Se registra `order_created` (teléfono enmascarado) y la métrica `OrdersCreated`.
8. **Seguimiento por polling.** `pedido.html?id=…&code=…` consulta cada 20 s, **se pausa** con la pestaña oculta y **se detiene** en estados finales (ADR-004).
9. **Operación en tienda.** El personal mueve el pedido en el panel; el cliente lo ve en ≤ 20 s. Al recoger, muestra el código.

## 3.4 Flujos del administrador

- **Login:** Authorization Code + PKCE contra el Hosted UI de Cognito; el access token (1 h) vive en `sessionStorage` y viaja como `Authorization: Bearer`. API Gateway valida el JWT **antes** de invocar Lambda.
- **Foto de producto:** el navegador convierte la imagen a **WebP** (máx. 1200 px, calidad 0,8) con `<canvas>` → pide una **URL prefirmada** (5 min) → la sube **directo a S3** (la Lambda nunca toca el archivo) → guarda el `imageKey`. Cada imagen tiene nombre único, así que se cachea sin invalidaciones.
- **Catálogo:** toda escritura de producto regenera `catalog.json` (lectura consistente, para no publicar un precio viejo). Los clientes ven el cambio en ≤ 60 s.

## 3.5 Máquina de estados del pedido

| Desde | Hacia | Quién | Efecto |
|---|---|---|---|
| Confirmado | En preparación | Admin | — |
| Confirmado | Cancelado | Cliente o admin | **Devuelve stock y libera el cupo** |
| En preparación | Listo para recoger | Admin | — |
| En preparación | Cancelado | Admin | **Devuelve stock y libera el cupo** |
| Listo para recoger | Entregado | Admin | — |
| Listo para recoger | No recogido | Admin o job de cierre | No devuelve stock (el pan ya se hizo) |
| Confirmado / En preparación | No recogido | Solo el job de cierre (18:30) | No devuelve stock |

`Entregado`, `Cancelado` y `No recogido` son **finales**. Cualquier otra transición se rechaza con `INVALID_TRANSITION`.

La validación es **atómica**: cada cambio de estado lleva una `ConditionExpression` sobre el estado actual. Si dos administradores pulsan a la vez, o el cliente cancela justo cuando el personal empieza a preparar, **solo uno gana** y el otro recibe `INVALID_TRANSITION` con el estado real (probado en los tests de carrera).

## 3.6 Análisis de concurrencia y cold starts

### Las carreras que importan: último cupo y último pan

El riesgo de negocio no es la cantidad de tráfico sino **dos clientes compitiendo por lo último**. Se resuelve sin locks, colas ni servidores, con una transacción de DynamoDB:

```
TransactWriteItems (todo o nada):
  [0]     slots     ADD count 1         IF  count no existe  OR  count < 10
  [1..n]  products  SET stock -= qty    IF  existe  AND  active = true  AND  stock >= qty
  [n+1]   orders    PUT pedido          IF  orderId no existe
  [n+2]   idempot.  PUT clave           IF  clave no existe (o ya venció)
```

- Si la franja tiene 9 pedidos y llegan dos a la vez, DynamoDB serializa las transacciones: **una** sube el contador a 10 y la otra falla la condición → `SLOT_FULL`. Como es todo o nada, el stock de la perdedora **no se descuenta**.
- El índice que falló en `CancellationReasons` dice exactamente qué pasó: `[0]` → franja llena; `[1..n]` → qué productos no alcanzan (`OUT_OF_STOCK` con sus `productId`); `[n+2]` → otra petición con la misma clave ganó (se devuelve su respuesta).
- **Cancelar** es la transacción inversa: cambia el estado (condición sobre el estado actual), devuelve el stock y resta 1 al contador.
- La **idempotencia** cubre los reintentos: el mismo cuerpo con la misma clave devuelve el mismo pedido (200), aunque la primera respuesta se haya perdido en la red; otro cuerpo con la misma clave → `IDEMPOTENCY_CONFLICT`.

Todo esto está cubierto por tests automáticos contra DynamoDB simulado (`moto`): último cupo, sin stock, atomicidad, idempotencia (repetición, conflicto y carrera), cancelación y carreras de estado.

### Concurrencia de Lambda

La concurrencia necesaria se estima como **peticiones por segundo × duración**:

| Fuente de tráfico (fin de semana, 3x) | Peticiones/día aprox. |
|---|---|
| Disponibilidad (~2 por sesión × 1.080 sesiones) | ~2.200 |
| Creación de pedidos (180 + reintentos) | ~200 |
| Polling del estado (~30 × 180 pedidos) | ~5.400 |
| Panel admin (refresco cada 30 s, 2 equipos × 12 h) + acciones | ~3.000 |
| **Total** | **~11.000 peticiones/día** |

En 12 horas de operación eso es ~0,25 req/s de promedio. Suponiendo que la hora pico concentra hasta 20 veces el promedio, el peor caso realista es **~4–6 req/s**. Con una duración típica de **~0,15 s** por invocación (una o dos operaciones de DynamoDB de un solo dígito de ms más la serialización):

> **Concurrencia ≈ 6 req/s × 0,15 s ≈ 1 entorno de ejecución simultáneo.**

Incluso multiplicando por 10 seguimos muy por debajo de la cuota de concurrencia de la cuenta (valor real verificado por Juan Pablo en Service Quotas: **PENDIENTE — dato de Juan Pablo**). Además:

- **El tráfico pesado no toca Lambda**: el catálogo y las imágenes (la mayoría de los bytes) salen de CloudFront.
- **La capacidad física acota las escrituras**: como mucho 220 pedidos/día; no tiene sentido aceptar más.
- **El throttling de API Gateway** (20 req/s con ráfaga de 40 por defecto, y 5/10 en `POST /api/orders`) protege la cuota de Lambda y la factura frente a abusos o bots: ante un exceso, el cliente recibe 429 y el front muestra "Hay mucha demanda, intenta en unos segundos".

### Cold starts

Un *cold start* ocurre cuando Lambda crea un entorno nuevo (primera invocación, después de un rato sin tráfico o al escalar). Lo mitigamos con decisiones de diseño, sin pagar por capacidad reservada:

| Decisión | Efecto |
|---|---|
| **Python 3.12 sobre ARM64 (Graviton)** | Runtime de arranque rápido; ARM64 además es ~20 % más barato por GB-s. |
| **Paquete mínimo sin dependencias** (`boto3` viene en el runtime; sin layers) | Menos código que descargar e importar. |
| **Clientes de `boto3` fuera del handler**, creados una vez por entorno | Las invocaciones "calientes" reutilizan la conexión TLS a DynamoDB. |
| **Sin VPC** | Sin el costo de adjuntar interfaces de red. |
| **256 MB** | Más CPU proporcional que el mínimo, sin pagar de más. |

Estimación: **unos cientos de milisegundos** solo en la primera invocación de cada entorno; las siguientes tardan decenas de ms. Medición real en `dev` (campo `Init Duration` de los logs `REPORT` de CloudWatch, consulta guardada `cold-starts`): **PENDIENTE — dato de Juan Pablo**.

**¿Por qué no Provisioned Concurrency?** Mantiene entornos calientes, pero **cobra por hora aunque no haya tráfico**. Para una panadería que vende 12 horas al día, con ~1 entorno concurrente y una latencia aceptable para un pedido de pan, el beneficio (evitar unos cientos de ms ocasionales) no justifica un costo fijo mensual. El costo cuantificado está en la sección de costos (Juan Pablo).
