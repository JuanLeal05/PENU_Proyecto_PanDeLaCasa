# 6. Observabilidad y operación

La observabilidad se implementa en [`infra/modules/app/observability.tf`](../../../infra/modules/app/observability.tf) y cumple el requisito del curso (**logs centralizados, métricas y alarmas**) con un costo mínimo aprovechando la capa gratuita de CloudWatch.

## 6.1 Logs centralizados y consultas guardadas

- **Retención:** 14 días en los 7 log groups de Lambda (`/aws/lambda/pdc-<env>-<fn>`) y en los access logs de API Gateway (`/aws/apigateway/pdc-<env>-api`).
- **Formato estructurado:** las Lambdas emiten **una línea JSON por evento** (`level`, `message`, `env`, `function`, `requestId`, `code`), enmascarando teléfono y correo (`300****567`).
- **Consultas guardadas en CloudWatch Logs Insights:**
  - `pdc-<env>/errores`: últimos 50 eventos `level = "ERROR"` en las 7 Lambdas.
  - `pdc-<env>/pedidos-por-franja`: conteo de `order_created` agrupado por `pickupSlot`.
  - `pdc-<env>/rechazos`: conteo de respuestas 4xx (`level = "WARNING"`) agrupado por `code`.
  - `pdc-<env>/cold-starts`: conteo, promedio y máximo de `@initDuration` en reportes `REPORT` por hora.
  - `pdc-<env>/api-5xx`: peticiones con `status >= 500` en API Gateway con `routeKey` e `integrationErrorMessage`.

## 6.2 Métricas y dashboard operativo (`pdc-<env>-operacion`)

El dashboard unifica métricas técnicas de AWS (`AWS/Lambda`, `AWS/ApiGateway`, `AWS/DynamoDB`, `AWS/CloudFront`) y **métricas de negocio** emitidas por el backend mediante **Embedded Metric Format (EMF)** en el namespace `PanDeLaCasa` (`OrdersCreated`, `OrdersCancelled`, `OrdersRejected` por `Reason`), sin llamadas adicionales a la API de CloudWatch.

| Fila del dashboard | Widgets incluidos |
|---|---|
| 1. Negocio | Pedidos creados y cancelados por hora; pedidos rechazados apilados por `Reason` |
| 2. API Gateway | Peticiones (`Count`), `4xx`, `5xx`; latencia `p95` e `IntegrationLatency` |
| 3. Lambda | Errores y throttles por función; duración `p95`; `ConcurrentExecutions` máximo con línea de cuota |
| 4. Datos y CDN | DynamoDB `ThrottledRequests` y `ConsumedWriteCapacityUnits`; CloudFront `Requests` y tasas `4xx`/`5xx` |
| 5. Logs | Tabla en vivo con la consulta `errores` sobre las 7 Lambdas |

## 6.3 Alarmas y runbook de respuesta

Las 6 alarmas por ambiente notifican al tópico SNS cifrado `pdc-<env>-alarmas` (suscripción por correo electrónico). Adicionalmente, AWS Budgets (`pdc-mensual`, USD 20) y Cost Anomaly Detection alertan por desviaciones de costo.

| Alarma | Condición | Severidad | Acción inmediata (runbook) |
|---|---|---|---|
| `pdc-<env>-lambda-errores` | Suma de `Errors` (7 Lambdas) ≥ 1 en 5 min | Crítica | Ejecutar consulta `errores` en Logs Insights; si viene de un deploy reciente, lanzar `rollback.yml`. |
| `pdc-<env>-api-5xx` | `5xx` ≥ 5 en 5 min | Crítica | Revisar consulta `api-5xx` e `integrationErrorMessage`; verificar estado de Lambda/DynamoDB y considerar rollback. |
| `pdc-<env>-lambda-throttles` | Suma de `Throttles` ≥ 1 en 5 min | Alta | Revisar `ConcurrentExecutions` en el dashboard; verificar si hay tráfico anómalo o si se requiere ajustar throttling. |
| `pdc-<env>-concurrencia` | `ConcurrentExecutions` máximo ≥ 80 % de cuota | Alta | Aviso preventivo previo al throttling; monitorear latencia de DynamoDB y posibles bucles de reintento. |
| `pdc-<env>-api-latencia` | `Latency` p95 > 1.500 ms por 3 periodos (15 min) | Media | Revisar `cold-starts` y `IntegrationLatency`; descartar degradación de red o saturación de DynamoDB. |
| `pdc-<env>-demanda-excede-capacidad` | `OrdersRejected{Reason=SLOT_FULL}` ≥ 20 en 1 h | Informativa | Señal de negocio: revisar en el panel admin si conviene ampliar `SLOT_CAPACITY` o abrir nuevas franjas. |
