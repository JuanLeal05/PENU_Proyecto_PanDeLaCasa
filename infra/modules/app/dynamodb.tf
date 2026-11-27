# Contrato 03: 4 tablas on-demand. PITR en orders y products; TTL en slots e idempotency.

resource "aws_dynamodb_table" "products" {
  name         = "${local.prefix}-products"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "productId"

  attribute {
    name = "productId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "orders" {
  name         = "${local.prefix}-orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "orderId"

  attribute {
    name = "orderId"
    type = "S"
  }

  attribute {
    name = "pickupDate"
    type = "S"
  }

  attribute {
    name = "slotKey"
    type = "S"
  }

  global_secondary_index {
    name            = "byDate"
    hash_key        = "pickupDate"
    range_key       = "slotKey"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "slots" {
  name         = "${local.prefix}-slots"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "date"
  range_key    = "slot"

  attribute {
    name = "date"
    type = "S"
  }

  attribute {
    name = "slot"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "idempotency" {
  name         = "${local.prefix}-idempotency"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idempotencyKey"

  attribute {
    name = "idempotencyKey"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }
}
