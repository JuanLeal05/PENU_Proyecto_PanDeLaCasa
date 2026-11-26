# 4. Seguridad e identidad

La estrategia de seguridad aplica defensa en profundidad sin introducir servidores ni costos fijos de red (sin VPC ni NAT Gateway). Todos los controles se definen en Terraform y se verifican en cada Pull Request con **Checkov** (`checkov -d infra --config-file .checkov.yaml`).

![Red y seguridad en AWS](../diagrams/png/03_red_seguridad.png)

*Figura 3. Fronteras de red, flujos HTTPS e identidades IAM/Cognito.*

## 4.1 Cifrado en tránsito y en reposo

- **HTTPS obligatorio en todo el recorrido:**
  - CloudFront redirige HTTP → HTTPS (`viewer_protocol_policy = "redirect-to-https"`) y adjunta la política gestionada `SecurityHeadersPolicy` (`Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`).
  - API Gateway HTTP API solo expone endpoints TLS.
  - Las URLs prefirmadas de subida de imágenes hacia S3 (`admin-products`) usan HTTPS, expiración de 300 s y firma SigV4.
  - Los buckets S3 (`tfstate`, `web`, `assets`) tienen política explícita `DenegarSinTLS` (`aws:SecureTransport = false` → `Deny`).
- **Cifrado en reposo:** DynamoDB usa cifrado administrado por AWS (`server_side_encryption`), S3 usa AES-256 (`SSE-S3`) con bloqueo total de acceso público (`block_public_* = true`), y el tópico SNS de alarmas usa `alias/aws/sns`.

## 4.2 Identidades y mínimo privilegio

| Actor / Componente | Mecanismo | Alcance exacto |
|---|---|---|
| **Cliente final** | Anónimo + código de 6 caracteres | Solo rutas públicas (`GET /api/health`, `GET /api/availability`, `POST /api/orders`, `GET/POST /api/orders/{id}*`). Comparación de `code` en tiempo constante y respuesta `404` ante código inválido para evitar enumeración. |
| **Administrador** | **Amazon Cognito** (Hosted UI + OAuth2 Authorization Code con PKCE) | Acceso a `/api/admin/*` validado por JWT Authorizer de API Gateway (`iss` + `aud`, token de 1 h). Creación exclusiva por administrador (`allow_admin_create_user_only = true`), contraseñas ≥ 12 caracteres y MFA TOTP opcional. |
| **7 funciones Lambda** | **1 rol IAM por función** (`pdc-<env>-lambda-<fn>`) | Acciones exactas de la matriz del contrato 03 §6 (por ejemplo, `admin-stats` solo tiene `dynamodb:Query` sobre `orders/index/byDate`). Logs restringidos a su propio log group. |
| **CloudFront → S3** | **Origin Access Control (OAC)** con SigV4 | Los buckets `web` y `assets` son 100 % privados; solo la distribución CloudFront (`AWS:SourceArn`) puede hacer `s3:GetObject`. |
| **EventBridge Scheduler** | Rol `pdc-<env>-scheduler` | Solo `lambda:InvokeFunction` sobre `pdc-<env>-scheduled-jobs`. |
| **GitHub Actions (CI/CD)** | **OIDC** (sin llaves estáticas en GitHub) | `pdc-github-plan` (solo lectura en PR), `pdc-github-dev` (environment `dev`) y `pdc-github-prod` (environment `prod` con aprobación manual). Ver ADR-006. |

## 4.3 Protección de la API, secretos y datos personales (Ley 1581)

- **Protección contra abuso:** throttling en API Gateway (20 req/s y ráfaga 40 global; 5 req/s y ráfaga 10 en `POST /api/orders`), validación estricta de esquema, cálculo de precios y totales únicamente en el servidor, e idempotencia con `Idempotency-Key` y hash del cuerpo.
- **Secretos fuera del código:** no existen credenciales en el repositorio; `.gitignore` excluye `config.js`, `*.tfstate*`, `*.local.tfvars` y `infra/bootstrap/terraform.tfvars`.
- **Protección de datos personales (Ley 1581 de 2012):** se solicitan únicamente nombre, teléfono y correo opcional con `dataConsent = true` obligatorio; los logs enmascaran teléfono y correo (`300****567`) y los fixtures de prueba usan datos ficticios. Como mejora futura se plantea agregar TTL de 12 meses sobre pedidos cerrados.
- **¿Por qué no hay VPC?** Todos los servicios (Lambda, DynamoDB, S3, Cognito) son endpoints regionales administrados con autenticación SigV4 e IAM. Encerrar las Lambdas en una VPC exigiría un NAT Gateway (~USD 32,85/mes) sin aumentar el aislamiento real y añadiría latencia de arranque en frío.
- **WAF opcional:** puede activarse un AWS WAFv2 en CloudFront (`AWSManagedRulesCommonRuleSet` + rate-limit de 300 req/5 min por IP, ~USD 7/mes); se mantiene apagado en el MVP por decisión FinOps y cabe dentro del presupuesto de USD 150/mes.
