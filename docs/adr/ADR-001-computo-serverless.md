# ADR-001 · Cómputo serverless con AWS Lambda

- **Estado:** Aceptado
- **Fecha:** 2026-11-24
- **Autor:** Juan

## Contexto

La lógica de negocio (disponibilidad, crear y cancelar pedidos, panel admin, jobs diarios) tiene que correr en algún lado. Las condiciones son:

- **Tráfico bajo e intermitente**: ~11.000 peticiones/día en el peor caso (fin de semana, 3x), concentradas entre 06:00 y 18:00. De noche, casi cero.
- **Pico físico acotado**: como mucho 220 pedidos/día (22 franjas × 10).
- Requisitos del curso: **≤ USD 150/mes**, 99,5 % de disponibilidad, soportar 3x la carga y mínimo privilegio.
- Equipo de dos personas sin tiempo para operar servidores (parches, escalado, monitoreo de SO).

## Alternativas

| | EC2 + Auto Scaling + ALB | ECS Fargate + ALB | **AWS Lambda** |
|---|---|---|---|
| Costo fijo mensual | ALB ≈ USD 16 + al menos 2 instancias para multi-AZ (≈ USD 12–15 con `t4g.micro`) | ALB ≈ USD 16 + al menos 2 tareas siempre encendidas (≈ USD 18+) | **USD 0** (sin tráfico no se paga) |
| Costo con nuestro volumen | El fijo domina: ≈ USD 30+/mes | ≈ USD 35+/mes | ~330.000 invocaciones/mes × ~0,15 s × 256 MB: dentro del nivel gratuito o centavos |
| Escalado al 3x | Políticas de Auto Scaling que hay que ajustar y probar | Auto Scaling de servicio | Automático, por invocación |
| Operación | Parches de SO, AMIs, agentes de logs | Imágenes de contenedor, registro (ECR) | Solo el código; logs a CloudWatch incluidos |
| Multi-AZ | Hay que configurarlo | Hay que configurarlo | Incluido |
| Red | VPC, subredes, security groups (y NAT si hay salida a internet) | Igual | Sin VPC |

## Decisión

Usamos **AWS Lambda** con **Python 3.12 sobre ARM64**, 256 MB y 10 s de timeout: **siete funciones**, una por responsabilidad, que comparten un mismo paquete (`backend/src`, sin dependencias externas) y difieren solo en el handler. Cada función tiene **su propio rol IAM** con las acciones mínimas de la matriz del contrato de datos.

## Consecuencias

**Positivas**

- **Costo casi cero** con nuestro volumen y **sin costo fijo**: nada cobra por hora. El ahorro frente a las alternativas (≥ USD 30/mes) es mayor que la factura completa de la arquitectura.
- **Escala sola** al 3x y más; la concurrencia estimada es ~1 entorno simultáneo (HLD §3.6).
- **Mínimo privilegio fino**: siete roles distintos; `admin-stats` ni siquiera puede escribir.
- **Sin servidores que parchar**; multi-AZ incluido.

**Negativas y cómo se mitigan**

- **Cold starts** de unos cientos de ms en la primera invocación de cada entorno → Python ARM64, paquete mínimo, clientes de `boto3` fuera del handler y sin VPC (HLD §3.6). No usamos Provisioned Concurrency porque cobra por hora sin tráfico.
- **Límites de la plataforma** (timeout de 15 min, cuota de concurrencia de la cuenta) → nuestras operaciones duran milisegundos; el throttling de API Gateway protege la cuota.
- **Acoplamiento a AWS** → el dominio (reglas, estados, validaciones) es Python puro y se prueba sin AWS; solo los repositorios y los handlers conocen Lambda y DynamoDB.
- **Depuración distribuida** → logs JSON con `requestId` en cada línea y métricas de negocio en formato EMF.
