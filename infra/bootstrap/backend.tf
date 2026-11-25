# Paso 3.4: tras el primer apply (state local), renombrar este archivo a
# backend.tf y ejecutar:
#   terraform init -migrate-state -backend-config="bucket=<state_bucket>"
terraform {
  backend "s3" {
    key          = "bootstrap/terraform.tfstate"
    region       = "us-east-2"
    use_lockfile = true
    encrypt      = true
  }
}
