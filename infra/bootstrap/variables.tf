variable "aws_region" {
  description = "Región de AWS. CR-001: us-east-2 por política de cuentas nuevas (el contrato 04 §9.3 decía us-east-1)."
  type        = string
  default     = "us-east-2"
}

variable "github_owner" {
  description = "Dueño del repositorio en GitHub (usuario u organización)."
  type        = string
}

variable "github_repo" {
  description = "Nombre del repositorio en GitHub (sin el dueño)."
  type        = string
}

variable "budget_emails" {
  description = "Correos que reciben las alertas del presupuesto mensual."
  type        = list(string)

  validation {
    condition     = length(var.budget_emails) > 0
    error_message = "Debe haber al menos un correo para las alertas de presupuesto."
  }
}

variable "monthly_budget_usd" {
  description = "Presupuesto mensual (COST) en USD."
  type        = number
  default     = 20
}
