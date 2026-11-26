data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = var.lambda_source_dir
  excludes    = ["**/__pycache__/**"]
  output_path = "${path.root}/.build/lambda.zip"
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.lambdas

  name              = "/aws/lambda/${local.prefix}-${each.key}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each = local.lambdas

  name               = "${local.prefix}-lambda-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy" "lambda" {
  for_each = local.lambdas

  name   = "permisos"
  role   = aws_iam_role.lambda[each.key].id
  policy = data.aws_iam_policy_document.lambda[each.key].json
}

resource "aws_lambda_function" "this" {
  for_each = local.lambdas

  function_name    = "${local.prefix}-${each.key}"
  role             = aws_iam_role.lambda[each.key].arn
  handler          = each.value
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = 256
  timeout          = 10
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = merge(
      {
        ENV       = var.env
        LOG_LEVEL = var.log_level
      },
      { for k in local.lambda_env_keys[each.key] : k => local.all_env[k] }
    )
  }

  # Sin reserved_concurrent_executions: la cuota de la cuenta podría no permitirlo.
  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.lambda]
}
