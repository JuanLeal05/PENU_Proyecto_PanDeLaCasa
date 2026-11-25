resource "aws_cognito_user_pool" "admins" {
  name                     = "${local.prefix}-admins"
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OPTIONAL"
  deletion_protection      = "INACTIVE" # para poder destruir al final del curso

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  software_token_mfa_configuration {
    enabled = true
  }
}

resource "aws_cognito_user_pool_domain" "admins" {
  domain       = "${local.prefix}-${local.account_id}"
  user_pool_id = aws_cognito_user_pool.admins.id
}

resource "aws_cognito_user_pool_client" "admin_web" {
  name         = "${local.prefix}-admin-web"
  user_pool_id = aws_cognito_user_pool.admins.id

  generate_secret                      = false
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  prevent_user_existence_errors        = "ENABLED"
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH"]

  callback_urls = concat(["${local.cloudfront_origin}/admin/index.html"], var.extra_callback_urls)
  logout_urls   = concat(["${local.cloudfront_origin}/admin/index.html"], var.extra_callback_urls)

  access_token_validity  = 1
  refresh_token_validity = 1

  token_validity_units {
    access_token  = "hours"
    refresh_token = "days"
  }
}
