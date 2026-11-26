# 5. Disponibilidad, respaldo y recuperación

## 5.1 Disponibilidad objetivo (≥ 99,5 % en horario comercial)

Todos los componentes de la ruta crítica son **administrados y multi-AZ por diseño** dentro de la región `us-east-2` (y CloudFront en el borde global). Según los acuerdos de nivel de servicio (SLA) públicos vigentes de AWS:

| Servicio en la ruta crítica | SLA mensual publicado por AWS | Notas |
|---|---|---|
| **Amazon CloudFront** | 99,9 % | Red global de ubicaciones de borde |
| **Amazon S3 (Standard)** | 99,9 % | Durabilidad 99,999999999 % (11 nueves), multi-AZ |
| **Amazon API Gateway (HTTP API)** | 99,95 % | Multi-AZ administrado |
| **AWS Lambda** | 99,95 % | Multi-AZ administrado |
| **Amazon DynamoDB (Single-Region)** | 99,99 % | Replicación síncrona en 3 AZ |
| **Amazon Cognito** | 99,9 % | Solo en el flujo de login del panel admin |

**Disponibilidad compuesta teórica del camino crítico de pedidos** (`CloudFront × API Gateway × Lambda × DynamoDB`):
$$0,999 \times 0,9995 \times 0,9995 \times 0,9999 \approx \mathbf{99,79\ \%}$$

Este valor supera el requisito del **99,5 %** en horario comercial (06:00–18:00), equivalente a un máximo de ~3,6 horas de indisponibilidad mensual. La disponibilidad real se mide de forma continua mediante la métrica `1 - (5xx / Count)` en el dashboard de CloudWatch.

## 5.2 Respaldo y recuperación (RPO ≤ 24 h / RTO ≤ 4 h)

- **RPO real ≈ 5 minutos (cumple RPO ≤ 24 h):**
  - **DynamoDB PITR (Point-in-Time Recovery)** habilitado en `orders` y `products`, permitiendo restaurar a cualquier segundo dentro de los últimos **35 días** (RPO efectivo de minutos). Las tablas `slots` e `idempotency` son efímeras con TTL (7 días y 24 h).
  - **Versionado de S3** habilitado en `web`, `assets` y `tfstate`, con retención de versiones no actuales de 30 días (`web`/`assets`) y 90 días (`tfstate`).
- **RTO estimado ≈ 20–45 minutos (cumple RTO ≤ 4 h):**
  1. **Infraestructura (~10–15 min):** ejecutar el pipeline de despliegue (`deploy.yml` o `terraform apply` en `infra/envs/<env>`) para recrear tablas, Lambdas, API, Cognito, CloudFront y subir los frontends desde Git.
  2. **Datos de DynamoDB (~10–25 min):** restaurar `pdc-<env>-orders` y `pdc-<env>-products` mediante PITR a una tabla temporal (`aws dynamodb restore-table-to-point-in-time`) y copiar o apuntar las variables de entorno `ORDERS_TABLE` / `PRODUCTS_TABLE` hacia las tablas restauradas (o recargar `seed_products.py` si es ambiente limpio).
  3. **Assets e imágenes (~2 min):** restaurar versiones anteriores en `pdc-<env>-assets-<accountId>` si hubo borrado accidental.

## 5.3 Escalabilidad 3x y degradación controlada

- **Carga 3x:** en temporada alta (~495.000 peticiones/mes, ~540 pedidos/día pico teórico acotado a 220 por capacidad física), DynamoDB On-Demand y Lambda escalan automáticamente. La concurrencia estimada promedio es ~1 ejecución simultánea (pico < 4), muy por debajo de la cuota de cuenta (mínimo 10).
- **Degradación controlada:** si un pico anómalo supera el umbral configurado, API Gateway aplica throttling (`429 Too Many Requests`, 20 req/s global y 5 req/s en `POST /api/orders`) antes de saturar la cuota de concurrencia de Lambda o generar costos descontrolados, y el frontend muestra un mensaje amigable al usuario.
