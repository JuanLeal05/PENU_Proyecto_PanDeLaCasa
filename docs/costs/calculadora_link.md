# AWS Pricing Calculator — Pan de la Casa

- **Fecha del estimado:** 2026-11-25
- **Región:** `us-east-2` (Ohio)
- **Enlace público (Save and share):** *(Pendiente: pegar aquí el enlace generado en https://calculator.aws/)*

## Pasos para completar el export oficial (Juan Pablo)

1. Abrir [AWS Pricing Calculator](https://calculator.aws/#/createCalculator) y crear dos grupos en un mismo estimado: **`MVP`** y **`Producción`** (región `us-east-2`).
2. Cargar los servicios y cantidades de la hoja `Supuestos` de [`costos_pan_de_la_casa.xlsx`](./costos_pan_de_la_casa.xlsx):
   - **AWS Lambda** (ARM64, 256 MB, 150 ms)
   - **Amazon API Gateway** (HTTP API)
   - **Amazon DynamoDB** (On-Demand, 4 tablas, PITR en 0,5 GB)
   - **Amazon S3** (Standard)
   - **Amazon CloudFront** (`PriceClass_100`)
   - **Amazon CloudWatch** (Logs, 2 dashboards, 12 alarmas)
   - **Amazon Cognito** (3 MAU)
   - **Amazon SNS** y **Amazon EventBridge Scheduler**
3. Hacer clic en **Save and share** → pegar la URL pública arriba.
4. Exportar el estimado como `calculadora_mvp.pdf` / `.csv` y `calculadora_produccion.pdf` / `.csv` en esta carpeta `docs/costs/`.
