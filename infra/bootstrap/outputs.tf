output "state_bucket" {
  description = "Bucket del state (variable de GitHub TF_STATE_BUCKET)."
  value       = aws_s3_bucket.state.id
}

output "plan_role_arn" {
  description = "Rol de plan para PRs (variable de GitHub AWS_PLAN_ROLE_ARN)."
  value       = aws_iam_role.plan.arn
}

output "dev_role_arn" {
  description = "Rol de despliegue de dev (variable AWS_ROLE_ARN del environment dev)."
  value       = aws_iam_role.deploy["dev"].arn
}

output "prod_role_arn" {
  description = "Rol de despliegue de prod (variable AWS_ROLE_ARN del environment prod)."
  value       = aws_iam_role.deploy["prod"].arn
}

output "account_id" {
  description = "ID de la cuenta de AWS."
  value       = local.account_id
}
