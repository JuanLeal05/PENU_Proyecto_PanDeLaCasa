# Pan de la Casa

Plataforma web serverless en AWS para la panadería **"Pan de la Casa"** (Bogotá): catálogo con fotos, pedidos para recoger en tienda en franjas de 30 minutos (máximo 10 pedidos por franja), seguimiento del estado del pedido y panel de administración.

Proyecto final del curso PENU — Escuela Colombiana de Ingeniería Julio Garavito.

## Arquitectura (resumen)

| Capa | Servicio |
|---|---|
| Presentación | CloudFront + S3 (sitio del cliente y panel admin) |
| API | API Gateway HTTP API + JWT de Cognito |
| Cómputo | AWS Lambda (Python 3.12, ARM64) |
| Datos | DynamoDB on-demand + S3 (imágenes y catálogo) |
| Jobs | EventBridge Scheduler |
| Operación | CloudWatch (logs, métricas y alarmas) |
| Entrega | Terraform + GitHub Actions (OIDC), ambientes `dev` y `prod` |

## Estructura del repositorio

```
backend/     # Lambdas en Python, dominio y tests
frontend/    # sitio del cliente (client/) y panel admin (admin/)
infra/       # Terraform
.github/     # pipelines de CI/CD
docs/        # HLD, ADR, diagramas, costos y despliegue
```

## Flujo de ramas

```
main  ←── PR (solo desde develop) ──  develop  ←── PR ──  feature/<cambio>
prod (con aprobación)                 dev (automático)
```

Todo cambio se hace en una rama `feature/<cambio>` que sale de `develop`.

## Integrantes

- Juan — aplicación (backend, frontends, HLD).
- Juan Pablo — plataforma (AWS, Terraform, CI/CD, costos).

> Este README se ampliará con las instrucciones de desarrollo local, las URLs de los ambientes y los enlaces a la documentación.
