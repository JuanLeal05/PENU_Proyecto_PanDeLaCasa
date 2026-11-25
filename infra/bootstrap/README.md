# Bootstrap de la cuenta AWS

Se aplica **una sola vez, a mano, por Juan Pablo**. Crea: bucket de state (`pdc-tfstate-<accountId>`), proveedor OIDC de GitHub, roles `pdc-github-plan|dev|prod` y el presupuesto `pdc-mensual`.

## Pasos manuales previos (consola)

Ver `docs/modules/juan-pablo/bootstrap_aws.md` §1: MFA en root, IAM Identity Center (perfil `pdc-admin`), plan/créditos, cuota de Lambda, Cost Explorer y Cost Anomaly Detection.

## Aplicar

```bash
export AWS_PROFILE=pdc-admin
aws sso login

cd infra/bootstrap
cp terraform.tfvars.example terraform.tfvars   # editar con correos reales (no se commitea)
terraform init
terraform plan -out tfplan
terraform apply tfplan
terraform output
```

## Migrar el state a S3 (recomendado)

```bash
mv backend.tf.example backend.tf
terraform init -migrate-state -backend-config="bucket=$(terraform output -raw state_bucket)"
```

## Configurar GitHub (rol Admin en el repo)

Variables del repositorio (*Settings → Secrets and variables → Actions → Variables*):

| Variable | Valor |
|---|---|
| `AWS_REGION` | `us-east-2` |
| `TF_STATE_BUCKET` | output `state_bucket` |
| `AWS_PLAN_ROLE_ARN` | output `plan_role_arn` |

Environments (*Settings → Environments*):

| Environment | Variables | Protección |
|---|---|---|
| `dev` | `AWS_ROLE_ARN` = `dev_role_arn`, `ALARM_EMAIL` | Deployment branches: solo `develop` |
| `prod` | `AWS_ROLE_ARN` = `prod_role_arn`, `ALARM_EMAIL` | Solo `main` + Required reviewers (Juan y Juan Pablo) |

Rulesets (*Settings → Rules → Rulesets → Import*): `github-rulesets/main.json`, `develop.json` y `solo-ramas-feature.json`. Los checks requeridos se activan tras la primera ejecución del CI.

## Notas de seguridad

- Sin llaves de AWS en GitHub: solo OIDC; cada rol lo asume un único `sub` (PR, environment `dev` o `prod`).
- Los roles de despliegue usan `PowerUserAccess` + IAM acotado a `pdc-<env>-*` (trade-off documentado en ADR-006) y un `Deny` explícito sobre el state del bootstrap y del otro ambiente.
