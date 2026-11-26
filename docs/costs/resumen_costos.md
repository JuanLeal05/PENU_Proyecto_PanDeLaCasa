# Resumen de costos y optimizaciones FinOps — Pan de la Casa

> **Región:** `us-east-2` (Ohio, según CR-001; los precios de lista equivalen a `us-east-1`).  
> **Restricción del curso:** ≤ USD 150/mes en producción.  
> **Archivo editable con fórmulas:** [`costos_pan_de_la_casa.xlsx`](./costos_pan_de_la_casa.xlsx).

---

## 1. Resumen por escenario

Todos los valores muestran **precio de lista sin Free Tier** (costo real de la arquitectura) y **con Free Tier** de AWS.

| Escenario | Mensual (sin Free Tier) | Anual (sin Free Tier) | Mensual (con Free Tier) | % del presupuesto ($150) |
|---|---:|---:|---:|---:|
| **MVP** (300 pedidos/mes, ~17.000 req) | **USD 7,61** | USD 91,31 | USD 0,27 | 5,1 % |
| **Producción** (2.760 pedidos/mes, ~165.000 req) | **USD 10,57** | USD 126,88 | USD 0,71 | 7,0 % |
| **Temporada alta (3x)** (8.280 pedidos/mes, ~495.000 req) | **USD 16,66** | USD 199,91 | USD 1,41 | 11,1 % |
| **Producción + WAF opcional** | **USD 17,57** | USD 210,88 | USD 7,71 | 11,7 % |

---

## 2. Desglose mensual y anual en Producción

Supuestos principales: 2.760 pedidos/mes, 16.560 sesiones, ~165.060 invocaciones Lambda (256 MB, 150 ms, ARM64), 50.000 WRU / 200.000 RRU en DynamoDB, 25 GB y 420.000 peticiones en CloudFront, 2 dashboards y 12 alarmas (dev + prod).

| Servicio | Mensual (sin Free Tier) | Anual (sin Free Tier) | Mensual (con Free Tier) |
|---|---:|---:|---:|
| **AWS Lambda (ARM64)** | USD 0,12 | USD 1,39 | USD 0,00 |
| **API Gateway HTTP API** | USD 0,17 | USD 1,98 | USD 0,00 |
| **DynamoDB (On-Demand + PITR)** | USD 0,34 | USD 4,05 | USD 0,34 |
| **CloudFront (`PriceClass_100`)** | USD 2,55 | USD 30,54 | USD 0,00 |
| **Amazon S3 (web + assets)** | USD 0,03 | USD 0,39 | USD 0,01 |
| **CloudWatch (logs, 2 dashboards, 12 alarmas)** | USD 7,36 | USD 88,32 | USD 0,36 |
| **Amazon Cognito (3 MAU)** | USD 0,02 | USD 0,20 | USD 0,00 |
| **SNS + EventBridge Scheduler** | USD 0,00 | USD 0,00 | USD 0,00 |
| **Total** | **USD 10,57** | **USD 126,88** | **USD 0,71** |

> Nota sobre CloudWatch: incluye los 2 dashboards (`dev` y `prod`) y las 12 alarmas (6 por ambiente). Con la capa gratuita permanente (3 dashboards y 10 alarmas), el costo baja a USD 0,20/mes por las 2 alarmas adicionales más USD 0,16 de ingesta/almacenamiento de logs.

---

## 3. Optimizaciones FinOps aplicadas

| ID | Optimización | Sin optimizar | Optimizado | Ahorro mensual | Ahorro anual | % |
|---|---|---:|---:|---:|---:|---:|
| **F1** | Catálogo estático (`catalog.json` en S3 + CloudFront) vs Lambda por consulta | USD 0,14 | USD 0,02 | USD 0,12 | USD 1,44 | 85,7 % |
| **F2** | API Gateway **HTTP API** ($1,00/M) vs REST API ($3,50/M) | USD 0,58 | USD 0,17 | USD 0,41 | USD 4,95 | 71,4 % |
| **F3** | Lambda **ARM64 (Graviton2)** vs x86_64 | USD 0,14 | USD 0,12 | USD 0,02 | USD 0,25 | 14,9 % |
| **F4** | **Sin VPC ni NAT Gateway** (no hay recursos privados) | USD 32,85 | USD 0,00 | USD 32,85 | USD 394,20 | 100,0 % |
| **F5** | **Sin Provisioned Concurrency** (mitigación por diseño) | USD 22,00 | USD 0,00 | USD 22,00 | USD 264,00 | 100,0 % |
| **F6** | Retención de logs **14 días** vs retención infinita | USD 0,25 | USD 0,03 | USD 0,22 | USD 2,64 | 88,0 % |
| **F7** | Imágenes **WebP** (~150 KB) vs JPEG (~600 KB) en CloudFront | USD 7,64 | USD 2,55 | USD 5,09 | USD 61,08 | 66,7 % |
| **F8** | Polling de **20 s con pausa y parada** vs 5 s continuo | USD 0,36 | USD 0,17 | USD 0,20 | USD 2,38 | 54,5 % |
| **F9** | CloudFront **`PriceClass_100`** vs `PriceClass_All` | USD 3,42 | USD 2,55 | USD 0,88 | USD 10,50 | 25,6 % |
| **F10** | Lifecycle S3: expirar versiones no actuales a 30 días | USD 0,12 | USD 0,03 | USD 0,09 | USD 1,08 | 75,0 % |

**Controles de gobierno FinOps adicionales:**
- Presupuesto `pdc-mensual` en AWS Budgets (USD 20/mes con alertas ACTUAL al 25 %, 50 %, 100 % y FORECASTED al 100 %).
- AWS Cost Anomaly Detection por servicio.
- Tags obligatorios en Terraform (`project`, `env`, `owner`, `managed-by`) para separar costos de `dev` y `prod` en Cost Explorer.
- Destrucción de los ambientes `dev` y `prod` al finalizar la sustentación (`terraform destroy`).

---

## 4. Comparativa de cómputo (soporte numérico del ADR-001)

| Alternativa | Mensual (USD) | Anual (USD) | Cumple ≤ $150 |
|---|---:|---:|---|
| **AWS Lambda (ARM64) + HTTP API (elegida)** | **USD 10,57** | **USD 126,88** | **Sí (7,0 %)** |
| EC2 (2× `t4g.small` Multi-AZ) + ALB + NAT | USD 83,67 | USD 1.004,04 | Sí, pero 7,9× más caro |
| ECS Fargate (2 tareas Multi-AZ) + ALB + NAT | USD 80,31 | USD 963,72 | Sí, pero 7,6× más caro |
