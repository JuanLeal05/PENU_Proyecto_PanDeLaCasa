# ADR-006 · Autenticación del pipeline con OIDC en cuenta propia

- **Estado:** Aceptado
- **Fecha:** 2026-11-25
- **Autor:** Juan Pablo

## Contexto

El pipeline de GitHub Actions necesita desplegar infraestructura en AWS (`dev` y `prod`), ejecutar `terraform plan` en los Pull Requests y sincronizar los archivos estáticos en S3. Debemos decidir en qué tipo de cuenta AWS desplegar y cómo autenticar GitHub Actions sin comprometer la seguridad.

## Alternativas

| | AWS Academy Learner Lab + llaves IAM | Cuenta propia + llaves IAM en GitHub Secrets | **Cuenta propia (Free Plan) + OIDC** |
|---|---|---|---|
| Servicios disponibles | Restringidos (sin roles IAM propios, sin CloudFront ni Cognito) | Todos los servicios | **Todos los servicios** |
| Duración de credenciales | Caducan cada ~4 h (rompe CI/CD automatizado) | Permanentes (riesgo alto si se filtran) | **Temporales (1 h)** emitidas por STS vía OIDC |
| Secretos en GitHub | Requiere rotar `AWS_ACCESS_KEY_ID`/`SECRET` manual | Requiere guardar llaves de larga duración | **Cero secretos**; solo ARNs de roles en variables |
| Separación `dev` / `prod` | Una sola sesión compartida | Posible, pero con múltiples pares de llaves | **Un rol por ambiente** con condición `sub` por environment |

## Decisión

Usamos una **cuenta propia de AWS (región `us-east-2` por política organizacional SCP, ver CR-001)** y autenticación federada mediante **GitHub OIDC (`aws_iam_openid_connect_provider`)** con tres roles dedicados:
1. `pdc-github-plan`: solo `ReadOnlyAccess` + lectura del bucket de state (`pull_request`).
2. `pdc-github-dev`: vinculado exclusivamente al GitHub Environment `dev` (`develop`).
3. `pdc-github-prod`: vinculado exclusivamente al GitHub Environment `prod` (`main`, con aprobación manual).

**Trade-off de permisos en despliegue:** mantener una política IAM acción-por-acción para Terraform sobre 7 servicios en un sprint de 3 días es propenso a bloqueos. Por ello, los roles `dev` y `prod` combinan `PowerUserAccess` (todos los servicios excepto IAM/Organizations) con una política inline **IAM acotada al prefijo `role/pdc-<env>-*`**, `iam:PassRole` restringido a `lambda.amazonaws.com` y `scheduler.amazonaws.com`, y un `Deny` explícito sobre el state del bootstrap y del otro ambiente.

## Consecuencias

**Positivas**
- **Cero credenciales estáticas** en el repositorio o en GitHub Secrets.
- **Aislamiento por ambiente**: un PR o la rama `develop` jamás puede asumir el rol de `prod` porque la condición `token.actions.githubusercontent.com:sub` de STS lo impide.
- **Trazabilidad**: CloudTrail registra la sesión federada con el repositorio, rama y ejecución de workflow.

**Negativas y cómo se mitigan**
- **`PowerUserAccess` es amplio**: en un entorno corporativo maduro se reemplazaría por *permission boundaries* o políticas granulares por servicio → aquí se mitiga con el `Deny` cruzado de state, el acotamiento de IAM a `pdc-<env>-*` y la **aprobación manual obligatoria** en el environment `prod`.
- **Restricción de región (`us-east-2`)**: la cuenta pertenece a una organización que restringe S3 a `us-east-2` → documentado en `CR-001` y parametrizado por variable en Terraform y GitHub.
