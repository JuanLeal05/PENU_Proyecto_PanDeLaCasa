data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.prefix}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
}

data "aws_iam_policy_document" "scheduler_invoke" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.this["scheduled-jobs"].arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "invocar-scheduled-jobs"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_invoke.json
}

locals {
  schedules = {
    "reset-stock" = { expression = "cron(30 5 * * ? *)", job = "reset_stock" }
    "close-day"   = { expression = "cron(30 18 * * ? *)", job = "close_day" }
  }
}

resource "aws_scheduler_schedule" "job" {
  for_each = local.schedules

  name                         = "${local.prefix}-${each.key}"
  schedule_expression          = each.value.expression
  schedule_expression_timezone = "America/Bogota"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.this["scheduled-jobs"].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ job = each.value.job })

    retry_policy {
      maximum_retry_attempts = 2
    }
  }
}
