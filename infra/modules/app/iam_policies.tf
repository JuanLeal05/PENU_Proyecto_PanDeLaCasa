# Matriz de permisos del contrato 03 §6: un documento por Lambda.
locals {
  t = {
    products    = aws_dynamodb_table.products.arn
    orders      = aws_dynamodb_table.orders.arn
    orders_idx  = "${aws_dynamodb_table.orders.arn}/index/byDate"
    slots       = aws_dynamodb_table.slots.arn
    idempotency = aws_dynamodb_table.idempotency.arn
  }

  iam_grants = {
    "public-availability" = [
      { actions = ["dynamodb:Scan", "dynamodb:GetItem"], resources = [local.t.products] },
      { actions = ["dynamodb:Query"], resources = [local.t.slots] },
    ]
    "create-order" = [
      { actions = ["dynamodb:BatchGetItem", "dynamodb:GetItem", "dynamodb:UpdateItem"], resources = [local.t.products] },
      { actions = ["dynamodb:UpdateItem"], resources = [local.t.slots] },
      { actions = ["dynamodb:PutItem"], resources = [local.t.orders] },
      { actions = ["dynamodb:GetItem", "dynamodb:PutItem"], resources = [local.t.idempotency] },
    ]
    "order-status" = [
      { actions = ["dynamodb:GetItem", "dynamodb:UpdateItem"], resources = [local.t.orders] },
      { actions = ["dynamodb:UpdateItem"], resources = [local.t.products, local.t.slots] },
    ]
    "admin-orders" = [
      { actions = ["dynamodb:Query"], resources = [local.t.orders, local.t.orders_idx] },
      { actions = ["dynamodb:GetItem", "dynamodb:UpdateItem"], resources = [local.t.orders] },
      { actions = ["dynamodb:UpdateItem"], resources = [local.t.products, local.t.slots] },
    ]
    "admin-products" = [
      { actions = ["dynamodb:Scan", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], resources = [local.t.products] },
      { actions = ["s3:PutObject"], resources = ["${aws_s3_bucket.assets.arn}/assets/*"] },
    ]
    "admin-stats" = [
      { actions = ["dynamodb:Query"], resources = [local.t.orders_idx] },
    ]
    "scheduled-jobs" = [
      { actions = ["dynamodb:Scan", "dynamodb:UpdateItem"], resources = [local.t.products] },
      { actions = ["dynamodb:Query"], resources = [local.t.orders_idx] },
      { actions = ["dynamodb:UpdateItem"], resources = [local.t.orders] },
    ]
  }
}

data "aws_iam_policy_document" "lambda" {
  for_each = local.lambdas

  dynamic "statement" {
    for_each = local.iam_grants[each.key]

    content {
      actions   = statement.value.actions
      resources = statement.value.resources
    }
  }

  # Logs solo de su propio log group.
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda[each.key].arn}:*"]
  }
}
