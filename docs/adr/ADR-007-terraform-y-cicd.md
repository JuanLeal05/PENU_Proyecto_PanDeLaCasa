# ADR-007 · Infraestructura como código con Terraform y GitHub Actions

- **Estado:** Aceptado
- **Fecha:** 2026-11-25
- **Autor:** Juan Pablo

## Contexto

La arquitectura incluye más de 100 recursos entre `dev` y `prod` (DynamoDB, 7 Lambdas, roles IAM, HTTP API, CloudFront, S3, Cognito, EventBridge Scheduler, CloudWatch y SNS). Necesitamos garantizar reproducibilidad (RTO ≤ 4 h), paridad entre ambientes, revisión de cambios antes de aplicar y despliegue automatizado con compuertas de calidad.

## Alternativas

| | Consola de AWS manual | AWS SAM / CloudFormation | **Terraform + GitHub Actions** |
|---|---|---|---|
| Paridad `dev` / `prod` | Muy baja, propensa a errores manuales | Buena, pero acoplada a YAML de CloudFormation | **Módulo único** `infra/modules/app` instanciado en `envs/{dev,prod}` |
| Revisión en Pull Request | Ninguna | Change sets difíciles de leer en PR | **`terraform plan` automático** en el resumen del PR |
| Análisis de seguridad estático | Ninguno | `cfn-nag` / `cfn-lint` | **Checkov** integrado en CI (`.checkov.yaml`) |
| Gestión de estado | N/A | Gestionada por AWS (stacks) | Bucket S3 cifrado con `use_lockfile = true` nativo (Terraform ≥ 1.10) |
| Experiencia del equipo | Baja escala | Media | **Alta** (ya validada en laboratorio previo del curso) |

## Decisión

Definimos toda la infraestructura en **Terraform (≥ 1.10)** con un módulo reutilizable (`infra/modules/app`) y backends separados en S3 (`app/dev/terraform.tfstate` y `app/prod/terraform.tfstate`) usando bloqueo nativo (`use_lockfile = true`). La orquestación corre en **GitHub Actions** siguiendo el flujo `feature/*` → `develop` (despliegue automático a `dev` + smoke test) → `main` (aprobación manual + despliegue a `prod` + smoke test), más un workflow `rollback.yml` por `workflow_dispatch`.

## Consecuencias

**Positivas**
- **RTO predecible**: destruir o recrear un ambiente completo toma ~10–15 minutos mediante `terraform apply` y la sincronización de frontends.
- **Calidad bloqueante**: ningún cambio se despliega si fallan `ruff`, `pytest` (< 70 % cobertura), `terraform fmt/validate` o `checkov`.
- **Promoción limpia**: el mismo código validado en `dev` se promueve a `prod` mediante PR `develop` → `main` con aprobación del compañero.

**Negativas y cómo se mitigan**
- **Gestión del state de bootstrap**: el bucket de state y los roles OIDC deben existir antes del primer pipeline → se aíslan en `infra/bootstrap/` (aplicado una sola vez y luego migrado a S3).
- **Tiempo de CloudFront**: crear o actualizar la distribución toma 5–10 min → los jobs de deploy tienen tolerancia y `smoke_test.sh` reintenta hasta 10 veces cada 15 s.
