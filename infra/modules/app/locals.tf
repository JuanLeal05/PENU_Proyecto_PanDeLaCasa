data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  prefix     = "pdc-${var.env}"
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  web_bucket_name    = "${local.prefix}-web-${local.account_id}"
  assets_bucket_name = "${local.prefix}-assets-${local.account_id}"

  cloudfront_origin = "https://${aws_cloudfront_distribution.main.domain_name}"
  cors_origins      = concat([local.cloudfront_origin], var.extra_cors_origins)

  # Las 7 funciones del contrato 04 §2: clave => handler.
  lambdas = {
    "public-availability" = "app.handlers.public_availability.handler"
    "create-order"        = "app.handlers.create_order.handler"
    "order-status"        = "app.handlers.order_status.handler"
    "admin-orders"        = "app.handlers.admin_orders.handler"
    "admin-products"      = "app.handlers.admin_products.handler"
    "admin-stats"         = "app.handlers.admin_stats.handler"
    "scheduled-jobs"      = "app.handlers.scheduled_jobs.handler"
  }

  # Las 14 rutas del contrato 02.
  routes = {
    "GET /api/health"                            = { lambda = "public-availability", auth = false }
    "GET /api/availability"                      = { lambda = "public-availability", auth = false }
    "POST /api/orders"                           = { lambda = "create-order", auth = false }
    "GET /api/orders/{orderId}"                  = { lambda = "order-status", auth = false }
    "POST /api/orders/{orderId}/cancel"          = { lambda = "order-status", auth = false }
    "GET /api/admin/orders"                      = { lambda = "admin-orders", auth = true }
    "PATCH /api/admin/orders/{orderId}/status"   = { lambda = "admin-orders", auth = true }
    "GET /api/admin/products"                    = { lambda = "admin-products", auth = true }
    "POST /api/admin/products"                   = { lambda = "admin-products", auth = true }
    "PUT /api/admin/products/{productId}"        = { lambda = "admin-products", auth = true }
    "DELETE /api/admin/products/{productId}"     = { lambda = "admin-products", auth = true }
    "POST /api/admin/products/{productId}/image" = { lambda = "admin-products", auth = true }
    "PUT /api/admin/inventory"                   = { lambda = "admin-products", auth = true }
    "GET /api/admin/stats"                       = { lambda = "admin-stats", auth = true }
  }

  # Valores de todas las variables de entorno posibles.
  all_env = {
    PRODUCTS_TABLE       = aws_dynamodb_table.products.name
    ORDERS_TABLE         = aws_dynamodb_table.orders.name
    ORDERS_BY_DATE_INDEX = "byDate"
    SLOTS_TABLE          = aws_dynamodb_table.slots.name
    IDEMPOTENCY_TABLE    = aws_dynamodb_table.idempotency.name
    ASSETS_BUCKET        = aws_s3_bucket.assets.id
    CATALOG_KEY          = "assets/catalog/catalog.json"
    IMAGES_PREFIX        = "assets/images/"
    ASSETS_BASE_URL      = local.cloudfront_origin
    SLOT_CAPACITY        = tostring(var.slot_capacity)
    OPEN_TIME            = var.open_time
    CLOSE_TIME           = var.close_time
    FIRST_SLOT           = var.first_slot
    LAST_SLOT            = var.last_slot
    SLOT_MINUTES         = tostring(var.slot_minutes)
    MIN_LEAD_MINUTES     = tostring(var.min_lead_minutes)
    MAX_UNITS_PER_ORDER  = tostring(var.max_units_per_order)
    MAX_LINES_PER_ORDER  = tostring(var.max_lines_per_order)
  }

  slot_env = ["SLOT_CAPACITY", "OPEN_TIME", "CLOSE_TIME", "FIRST_SLOT", "LAST_SLOT", "SLOT_MINUTES", "MIN_LEAD_MINUTES"]

  # Qué variables recibe cada Lambda (tabla del contrato 04 §2).
  lambda_env_keys = {
    "public-availability" = concat(["PRODUCTS_TABLE", "SLOTS_TABLE", "ASSETS_BASE_URL"], local.slot_env)
    "create-order"        = concat(["PRODUCTS_TABLE", "ORDERS_TABLE", "SLOTS_TABLE", "IDEMPOTENCY_TABLE", "MAX_UNITS_PER_ORDER", "MAX_LINES_PER_ORDER"], local.slot_env)
    "order-status"        = ["PRODUCTS_TABLE", "ORDERS_TABLE", "SLOTS_TABLE"]
    "admin-orders"        = ["PRODUCTS_TABLE", "ORDERS_TABLE", "ORDERS_BY_DATE_INDEX", "SLOTS_TABLE"]
    "admin-products"      = ["PRODUCTS_TABLE", "ASSETS_BUCKET", "CATALOG_KEY", "IMAGES_PREFIX", "ASSETS_BASE_URL"]
    "admin-stats"         = ["ORDERS_TABLE", "ORDERS_BY_DATE_INDEX"]
    "scheduled-jobs"      = ["PRODUCTS_TABLE", "ORDERS_TABLE", "ORDERS_BY_DATE_INDEX"]
  }
}
