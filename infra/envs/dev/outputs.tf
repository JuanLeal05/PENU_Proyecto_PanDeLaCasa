output "env" {
  value = module.app.env
}

output "aws_region" {
  value = module.app.aws_region
}

output "api_base_url" {
  value = module.app.api_base_url
}

output "cloudfront_domain" {
  value = module.app.cloudfront_domain
}

output "cloudfront_distribution_id" {
  value = module.app.cloudfront_distribution_id
}

output "web_bucket" {
  value = module.app.web_bucket
}

output "assets_bucket" {
  value = module.app.assets_bucket
}

output "cognito_user_pool_id" {
  value = module.app.cognito_user_pool_id
}

output "cognito_client_id" {
  value = module.app.cognito_client_id
}

output "cognito_domain" {
  value = module.app.cognito_domain
}
