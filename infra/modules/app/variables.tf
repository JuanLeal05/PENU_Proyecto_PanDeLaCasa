variable "env" {
  description = "Ambiente: dev o prod."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env debe ser dev o prod."
  }
}

variable "lambda_source_dir" {
  description = "Carpeta backend/src que se comprime y se despliega en todas las Lambdas."
  type        = string
}

variable "alarm_email" {
  description = "Correo que recibe las alarmas (lo usa observability.tf)."
  type        = string
  default     = ""
}

variable "extra_cors_origins" {
  description = "Orígenes extra para CORS de la API y del bucket de assets (p. ej. localhost en dev)."
  type        = list(string)
  default     = []
}

variable "extra_callback_urls" {
  description = "URLs extra de callback/logout de Cognito."
  type        = list(string)
  default     = []
}

variable "log_retention_days" {
  description = "Retención de los log groups."
  type        = number
  default     = 14
}

variable "log_level" {
  description = "Variable LOG_LEVEL de las Lambdas."
  type        = string
  default     = "INFO"
}

variable "lambda_concurrency_quota" {
  description = "Cuota de ejecuciones concurrentes de Lambda en la cuenta (bootstrap_aws.md §1.4)."
  type        = number
  default     = 10
}

# Throttling (contrato 01 §4)
variable "api_default_rate" {
  type    = number
  default = 20
}

variable "api_default_burst" {
  type    = number
  default = 40
}

variable "orders_rate" {
  type    = number
  default = 5
}

variable "orders_burst" {
  type    = number
  default = 10
}

# Reglas de negocio expuestas como variables de entorno (contrato 04 §2)
variable "slot_capacity" {
  type    = number
  default = 10
}

variable "open_time" {
  type    = string
  default = "06:00"
}

variable "close_time" {
  type    = string
  default = "18:00"
}

variable "first_slot" {
  type    = string
  default = "07:00"
}

variable "last_slot" {
  type    = string
  default = "17:30"
}

variable "slot_minutes" {
  type    = number
  default = 30
}

variable "min_lead_minutes" {
  type    = number
  default = 30
}

variable "max_units_per_order" {
  type    = number
  default = 20
}

variable "max_lines_per_order" {
  type    = number
  default = 10
}
