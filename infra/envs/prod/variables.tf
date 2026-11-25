variable "aws_region" {
  description = "Región de AWS (CR-001: us-east-2)."
  type        = string
  default     = "us-east-2"
}

variable "alarm_email" {
  description = "Correo de alarmas (variable ALARM_EMAIL del environment de GitHub)."
  type        = string
  default     = ""
}

variable "extra_cors_origins" {
  type    = list(string)
  default = []
}

variable "extra_callback_urls" {
  type    = list(string)
  default = []
}
