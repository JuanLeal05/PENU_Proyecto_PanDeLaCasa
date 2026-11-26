# Exactamente los outputs del contrato 04 §6.
output "env" {
  value = var.env
}

output "aws_region" {
  value = local.region
}

output "api_base_url" {
  value = aws_apigatewayv2_api.api.api_endpoint
}

output "cloudfront_domain" {
  value = local.web_domain
}

output "cloudfront_distribution_id" {
  value = var.enable_cloudfront ? aws_cloudfront_distribution.main[0].id : ""
}

output "web_bucket" {
  value = aws_s3_bucket.web.id
}

output "assets_bucket" {
  value = aws_s3_bucket.assets.id
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.admins.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.admin_web.id
}

output "cognito_domain" {
  value = "https://${aws_cognito_user_pool_domain.admins.domain}.auth.${local.region}.amazoncognito.com"
}
