# 2. Requisitos y supuestos

## 2.1 Requisitos funcionales

| ID | Requisito | Actor | Dónde se implementa |
|---|---|---|---|
| RF-01 | Ver el catálogo agrupado por categoría, con foto, descripción y precio | Cliente | `catalog.json` estático en S3 + CloudFront (ADR-003) |
| RF-02 | Ver la disponibilidad de hoy: tienda abierta/cerrada, cupos por franja y stock por producto | Cliente | `GET /api/availability` |
| RF-03 | Crear un pedido para hoy eligiendo una franja, con nombre, celular, email opcional y consentimiento de datos | Cliente | `POST /api/orders` (transacción, idempotencia) |
| RF-04 | Consultar el estado del pedido con `orderId` + código | Cliente | `GET /api/orders/{orderId}?code=` + polling (ADR-004) |
| RF-05 | Cancelar el pedido mientras esté "Confirmado" (devuelve stock y libera el cupo) | Cliente | `POST /api/orders/{orderId}/cancel` |
| RF-06 | Ver los pedidos del día agrupados por franja y filtrarlos por estado | Admin | `GET /api/admin/orders` |
| RF-07 | Cambiar el estado de un pedido según la máquina de estados (§3.5) | Admin | `PATCH /api/admin/orders/{orderId}/status` |
| RF-08 | Crear, editar, activar/desactivar productos; el catálogo público se regenera solo | Admin | `/api/admin/products` (CRUD) |
| RF-09 | Subir la foto de un producto (optimizada a WebP en el navegador) | Admin | URL prefirmada de S3 |
| RF-10 | Ajustar el stock y la producción diaria | Admin | `PUT /api/admin/inventory` |
| RF-11 | Ver estadísticas del día: pedidos por estado, ingresos entregados, unidades por producto, pedidos por franja | Admin | `GET /api/admin/stats` |
| RF-12 | Restablecer el stock a las 05:30 y cerrar el día a las 18:30 | Sistema | Lambda `scheduled-jobs` + EventBridge Scheduler |
| RF-13 | Iniciar sesión en el panel (sin registro público) | Admin | Cognito Hosted UI + PKCE |

## 2.2 Requisitos no funcionales del curso

| ID | Requisito | Cómo se cumple | Cómo se verifica |
|---|---|---|---|
| RNF-01 | **Costo ≤ USD 150/mes** en producción | Solo servicios con pago por uso (Lambda, DynamoDB on-demand, API Gateway HTTP, S3, CloudFront); **ningún recurso cobra por hora** (sin EC2, ALB, NAT ni RDS). El catálogo sale de CDN. | Estimación con la calculadora de AWS y AWS Budgets con alerta (sección de costos, Juan Pablo). |
| RNF-02 | **99,5 % de disponibilidad** en horario comercial | Todos los servicios son administrados y multi-AZ por diseño; no hay servidores propios ni puntos únicos de falla. | Disponibilidad compuesta con los SLA de AWS (§5) + smoke test en cada despliegue + alarmas. |
| RNF-03 | **HTTPS** en todo | CloudFront redirige HTTP→HTTPS; API Gateway y las URLs prefirmadas de S3 solo sirven HTTPS. | Smoke test y revisión de la configuración (§4). |
| RNF-04 | **Secretos fuera del código** | La aplicación no tiene secretos: Cognito usa PKCE (cliente público), el pipeline usa OIDC (sin llaves), y la configuración del front se genera en el despliegue (`config.js`). | Checkov en CI, `.gitignore`, búsqueda de URLs quemadas en el front (§4). |
| RNF-05 | **Mínimo privilegio** | Un rol IAM por Lambda con solo las acciones de la matriz del contrato de datos; buckets privados con OAC. | Revisión de la matriz vs. las llamadas del código (hecha en el backend) + Checkov. |
| RNF-06 | **RPO 24 h / RTO 4 h** | DynamoDB con PITR (RPO de minutos), S3 versionado, infraestructura recreable con Terraform. | Procedimiento de restauración documentado y probado (§5). |
| RNF-07 | **Soportar 3x la carga** | Escalado automático por demanda (Lambda, DynamoDB on-demand, CloudFront). El techo real es físico: 220 pedidos/día. | Análisis de concurrencia (§3.6) + throttling + cuota de Lambda (§5). |
| RNF-08 | **Logs, métricas y al menos una alarma** | Logs JSON por evento, métricas de negocio en formato EMF (`OrdersCreated`, `OrdersRejected`, `OrdersCancelled`), dashboard y alarmas con SNS. | Dashboard y prueba de alarma (§6). |
| RNF-09 | **Datos personales (Ley 1581 de 2012)** | Datos mínimos (nombre, celular, email opcional), consentimiento explícito obligatorio, teléfono y email **enmascarados en logs** (`300****567`). | Test automático `test_logs_mask_pii` + revisión (§4). |
| RNF-10 | **Calidad del código** | Lint y formato con `ruff`, 270+ tests con `pytest` + `moto`, cobertura ≥ 70 % obligatoria en CI (actual: ~97 %). | Job `backend` del pipeline, requerido para hacer merge. |

## 2.3 Supuestos del negocio

Acordados en el contrato de reglas de negocio. Son la base de todo el diseño: si cambian, cambian la capacidad y los costos.

| # | Supuesto | Valor | Consecuencia en el diseño |
|---|---|---|---|
| S1 | Zona horaria | Bogotá, UTC−5 sin horario de verano | El código usa un offset fijo de −5 h (no depende de `tzdata`); la hora se inyecta para poder probarla. |
| S2 | Horario de pedidos web | 06:00 a 18:00 | Fuera de horario la API responde `STORE_CLOSED`. |
| S3 | Franjas de recogida | Cada 30 min, de 07:00 a 17:30 → **22 franjas** | Una fila por franja usada en la tabla `slots`. |
| S4 | Capacidad por franja | **10 pedidos** | Condición `count < 10` dentro de la transacción. |
| S5 | Anticipación mínima | La franja debe empezar ≥ 30 min después del pedido | `SLOT_NOT_AVAILABLE` si no se cumple. |
| S6 | Día del pedido | Solo el mismo día | Sin calendario; el stock es la producción del día. |
| S7 | Límites por pedido | ≤ 20 unidades y ≤ 10 productos distintos | Validación en el front y en el backend. |
| S8 | Inventario | Producción diaria; se restablece a las 05:30 | Job `reset_stock`; el admin puede ajustarlo. |
| S9 | Pago | En tienda al recoger | Sin pasarela: PCI fuera del alcance. |
| S10 | Cliente | Sin cuenta; nombre, celular (10 dígitos, empieza por 3), email opcional y consentimiento | Validación y `dataConsent: true` obligatorio. |
| S11 | Consulta del pedido | `orderId` + código de 6 caracteres | Código sin caracteres ambiguos (sin O/0/I/1); comparación en tiempo constante. |
| S12 | Administradores | 2–3 personas, sin registro público | Usuarios creados por Juan Pablo en Cognito. |
| S13 | Moneda | Pesos colombianos, enteros | Todos los montos son enteros; no hay redondeos. |
| S14 | Cierre del día | 18:30: lo pendiente pasa a "No recogido" | Job `close_day`. |

### Volumen esperado

| Métrica | Entre semana | Fin de semana (3x) |
|---|---|---|
| Pedidos/día | 60 | 180 |
| Visitas/día (sesiones) | ~360 | ~1.080 |
| Días/mes | 22 | 8 |

- **Pedidos/mes** ≈ 22 × 60 + 8 × 180 = **2.760**.
- **Techo físico**: 22 franjas × 10 pedidos = **220 pedidos/día**. El fin de semana (180) cabe con ~18 % de margen; el sistema nunca acepta más de lo que la panadería puede despachar.
- **Polling**: cada 20 s mientras el pedido no esté en un estado final → ~30 consultas por pedido en promedio.
- **Catálogo**: ~40 productos con imágenes WebP de ~150 KB, servidas desde CDN.
