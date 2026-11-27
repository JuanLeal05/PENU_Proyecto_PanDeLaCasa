# Observabilidad: consultas guardadas, dashboard, tópico SNS y alarmas (observabilidad.md).

locals {
  lambda_log_group_names = [for k in keys(local.lambdas) : aws_cloudwatch_log_group.lambda[k].name]
  lambda_keys_sorted     = sort(keys(local.lambdas))
}

# -----------------------------------------------------------------------------
# 1. Consultas guardadas de CloudWatch Logs Insights (gratis)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_query_definition" "errores" {
  name            = "${local.prefix}/errores"
  log_group_names = local.lambda_log_group_names
  query_string    = <<-EOT
    fields @timestamp, function, requestId, message, error
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 50
  EOT
}

resource "aws_cloudwatch_query_definition" "pedidos_por_franja" {
  name            = "${local.prefix}/pedidos-por-franja"
  log_group_names = [aws_cloudwatch_log_group.lambda["create-order"].name]
  query_string    = <<-EOT
    filter message = "order_created"
    | stats count() by pickupSlot
    | sort pickupSlot asc
  EOT
}

resource "aws_cloudwatch_query_definition" "rechazos" {
  name            = "${local.prefix}/rechazos"
  log_group_names = [aws_cloudwatch_log_group.lambda["create-order"].name]
  query_string    = <<-EOT
    filter level = "WARNING" and ispresent(code)
    | stats count() by code
  EOT
}

resource "aws_cloudwatch_query_definition" "cold_starts" {
  name            = "${local.prefix}/cold-starts"
  log_group_names = local.lambda_log_group_names
  query_string    = <<-EOT
    filter @type = "REPORT" and ispresent(@initDuration)
    | stats count(), avg(@initDuration), max(@initDuration) by bin(1h)
  EOT
}

resource "aws_cloudwatch_query_definition" "api_5xx" {
  name            = "${local.prefix}/api-5xx"
  log_group_names = [aws_cloudwatch_log_group.api.name]
  query_string    = <<-EOT
    filter status >= 500
    | fields @timestamp, routeKey, integrationErrorMessage
    | sort @timestamp desc
    | limit 50
  EOT
}

# -----------------------------------------------------------------------------
# 2. SNS para notificaciones de alarmas
# Sin kms_master_key_id = "alias/aws/sns": CloudWatch Alarms no tiene permisos
# sobre la clave gestionada de SNS (solo funciona con CMK o sin KMS).
# -----------------------------------------------------------------------------
resource "aws_sns_topic" "alarmas" {
  name = "${local.prefix}-alarmas"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarmas.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# -----------------------------------------------------------------------------
# 3. Dashboard de operación (los 3 primeros dashboards de la cuenta son gratis)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_dashboard" "operacion" {
  dashboard_name = "${local.prefix}-operacion"

  dashboard_body = jsonencode({
    widgets = [
      # Fila 1: Negocio
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Negocio: pedidos creados y cancelados"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 3600
          stat    = "Sum"
          metrics = [
            ["PanDeLaCasa", "OrdersCreated", "Env", var.env, { label = "Creados" }],
            ["PanDeLaCasa", "OrdersCancelled", "Env", var.env, { label = "Cancelados" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Negocio: pedidos rechazados por motivo"
          region  = local.region
          view    = "timeSeries"
          stacked = true
          period  = 3600
          stat    = "Sum"
          metrics = [
            ["PanDeLaCasa", "OrdersRejected", "Env", var.env, "Reason", "SLOT_FULL"],
            ["PanDeLaCasa", "OrdersRejected", "Env", var.env, "Reason", "OUT_OF_STOCK"],
            ["PanDeLaCasa", "OrdersRejected", "Env", var.env, "Reason", "STORE_CLOSED"],
            ["PanDeLaCasa", "OrdersRejected", "Env", var.env, "Reason", "SLOT_NOT_AVAILABLE"],
          ]
        }
      },
      # Fila 2: API Gateway
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "API Gateway: peticiones, 4xx y 5xx"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", aws_apigatewayv2_api.api.id, "Stage", "$default", { id = "m_count" }],
            ["AWS/ApiGateway", "4xx", "ApiId", aws_apigatewayv2_api.api.id, "Stage", "$default"],
            ["AWS/ApiGateway", "5xx", "ApiId", aws_apigatewayv2_api.api.id, "Stage", "$default", { id = "m_5xx" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "API Gateway: latencia p95 (ms)"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "p95"
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiId", aws_apigatewayv2_api.api.id, "Stage", "$default"],
            ["AWS/ApiGateway", "IntegrationLatency", "ApiId", aws_apigatewayv2_api.api.id, "Stage", "$default"],
          ]
        }
      },
      # Fila 3: Lambda
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "Lambda: errores y throttles por función"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          metrics = concat(
            [for k in local.lambda_keys_sorted : ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.this[k].function_name, { label = "${k} Errors" }]],
            [for k in local.lambda_keys_sorted : ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.this[k].function_name, { label = "${k} Throttles" }]]
          )
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "Lambda: duración p95 (ms)"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "p95"
          metrics = [
            for k in local.lambda_keys_sorted : ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.this[k].function_name, { label = k }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "Lambda: concurrencia máxima vs cuota"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Maximum"
          metrics = [
            ["AWS/Lambda", "ConcurrentExecutions"],
          ]
          annotations = {
            horizontal = [
              {
                label = "Cuota de cuenta"
                value = var.lambda_concurrency_quota
                color = "#d62728"
              }
            ]
          }
        }
      },
      # Fila 4: Datos y CDN
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 12
        height = 6
        properties = {
          title   = "DynamoDB: throttles y WCU consumidas"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          metrics = [
            ["AWS/DynamoDB", "ThrottledRequests", "TableName", aws_dynamodb_table.products.name],
            ["AWS/DynamoDB", "ThrottledRequests", "TableName", aws_dynamodb_table.orders.name],
            ["AWS/DynamoDB", "ThrottledRequests", "TableName", aws_dynamodb_table.slots.name],
            ["AWS/DynamoDB", "ThrottledRequests", "TableName", aws_dynamodb_table.idempotency.name],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", aws_dynamodb_table.orders.name],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", aws_dynamodb_table.slots.name],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 18
        width  = 12
        height = 6
        properties = {
          title   = var.enable_cloudfront ? "CloudFront: peticiones y tasa de errores" : "Web Proxy (sin CloudFront): invocaciones y errores"
          region  = var.enable_cloudfront ? "us-east-1" : local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          metrics = concat(
            [for d in aws_cloudfront_distribution.main : ["AWS/CloudFront", "Requests", "DistributionId", d.id, "Region", "Global", { stat = "Sum" }]],
            [for d in aws_cloudfront_distribution.main : ["AWS/CloudFront", "4xxErrorRate", "DistributionId", d.id, "Region", "Global", { stat = "Average", yAxis = "right" }]],
            [for d in aws_cloudfront_distribution.main : ["AWS/CloudFront", "5xxErrorRate", "DistributionId", d.id, "Region", "Global", { stat = "Average", yAxis = "right" }]],
            [for fn in aws_lambda_function.web_proxy : ["AWS/Lambda", "Invocations", "FunctionName", fn.function_name, { stat = "Sum" }]],
            [for fn in aws_lambda_function.web_proxy : ["AWS/Lambda", "Errors", "FunctionName", fn.function_name, { stat = "Sum", yAxis = "right" }]],
          )
        }
      },
      # Fila 5: Logs de errores
      {
        type   = "log"
        x      = 0
        y      = 24
        width  = 24
        height = 6
        properties = {
          title  = "Últimos errores en Lambdas"
          region = local.region
          query  = "SOURCE ${join(" | SOURCE ", local.lambda_log_group_names)} | fields @timestamp, function, requestId, message, error | filter level = \"ERROR\" | sort @timestamp desc | limit 50"
          view   = "table"
        }
      },
    ]
  })
}

# -----------------------------------------------------------------------------
# 4. Alarmas → SNS por email
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "lambda_errores" {
  alarm_name          = "${local.prefix}-lambda-errores"
  alarm_description   = "Cualquier error no controlado en las 7 Lambdas."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarmas.arn]
  ok_actions          = [aws_sns_topic.alarmas.arn]

  metric_query {
    id          = "total_errors"
    expression  = join(" + ", [for i, _ in local.lambda_keys_sorted : "e${i}"])
    label       = "Total errores Lambda"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = { for i, k in local.lambda_keys_sorted : "e${i}" => k }

    content {
      id          = metric_query.key
      return_data = false

      metric {
        metric_name = "Errors"
        namespace   = "AWS/Lambda"
        period      = 300
        stat        = "Sum"
        dimensions = {
          FunctionName = aws_lambda_function.this[metric_query.value].function_name
        }
      }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.prefix}-api-5xx"
  alarm_description   = "5xx >= 5 en 5 min en API Gateway (afecta disponibilidad)."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarmas.arn]
  ok_actions          = [aws_sns_topic.alarmas.arn]

  dimensions = {
    ApiId = aws_apigatewayv2_api.api.id
    Stage = "$default"
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  alarm_name          = "${local.prefix}-lambda-throttles"
  alarm_description   = "Throttling en cualquiera de las 7 Lambdas."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarmas.arn]
  ok_actions          = [aws_sns_topic.alarmas.arn]

  metric_query {
    id          = "total_throttles"
    expression  = join(" + ", [for i, _ in local.lambda_keys_sorted : "t${i}"])
    label       = "Total throttles Lambda"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = { for i, k in local.lambda_keys_sorted : "t${i}" => k }

    content {
      id          = metric_query.key
      return_data = false

      metric {
        metric_name = "Throttles"
        namespace   = "AWS/Lambda"
        period      = 300
        stat        = "Sum"
        dimensions = {
          FunctionName = aws_lambda_function.this[metric_query.value].function_name
        }
      }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "concurrencia" {
  alarm_name          = "${local.prefix}-concurrencia"
  alarm_description   = "Concurrencia de Lambda >= 80 % de la cuota de cuenta."
  namespace           = "AWS/Lambda"
  metric_name         = "ConcurrentExecutions"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = floor(var.lambda_concurrency_quota * 0.8)
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarmas.arn]
  ok_actions          = [aws_sns_topic.alarmas.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_latencia" {
  alarm_name          = "${local.prefix}-api-latencia"
  alarm_description   = "Latencia p95 > 1500 ms durante 3 periodos de 5 min."
  namespace           = "AWS/ApiGateway"
  metric_name         = "Latency"
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 3
  threshold           = 1500
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarmas.arn]
  ok_actions          = [aws_sns_topic.alarmas.arn]

  dimensions = {
    ApiId = aws_apigatewayv2_api.api.id
    Stage = "$default"
  }
}

resource "aws_cloudwatch_metric_alarm" "demanda_excede_capacidad" {
  alarm_name          = "${local.prefix}-demanda-excede-capacidad"
  alarm_description   = "Señal de negocio: rechazos por franja llena >= 20 en 1 h."
  namespace           = "PanDeLaCasa"
  metric_name         = "OrdersRejected"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 20
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarmas.arn]
  ok_actions          = [aws_sns_topic.alarmas.arn]

  dimensions = {
    Env    = var.env
    Reason = "SLOT_FULL"
  }
}
