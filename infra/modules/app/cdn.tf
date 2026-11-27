# Políticas gestionadas por AWS.
locals {
  cache_policy_caching_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  response_policy_security       = "67f7725c-6f97-4210-82d7-5512b31e9d03"
}

resource "aws_cloudfront_origin_access_control" "this" {
  for_each = var.enable_cloudfront ? local.bucket_ids : {}

  name                              = "${local.prefix}-${each.key}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Nota: WAF (enable_waf) no se implementa: los WAF de CloudFront exigen el
# provider en us-east-1 y la decisión FinOps es dejarlo desactivado.
resource "aws_cloudfront_distribution" "main" {
  count = var.enable_cloudfront ? 1 : 0

  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = "PriceClass_100"
  default_root_object = "index.html"
  comment             = "${local.prefix} sitio cliente, admin y assets"

  origin {
    origin_id                = "web"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.this["web"].id
  }

  origin {
    origin_id                = "assets"
    domain_name              = aws_s3_bucket.assets.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.this["assets"].id
  }

  default_cache_behavior {
    target_origin_id           = "web"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = local.cache_policy_caching_optimized
    response_headers_policy_id = local.response_policy_security
    compress                   = true
  }

  ordered_cache_behavior {
    path_pattern               = "/assets/*"
    target_origin_id           = "assets"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = local.cache_policy_caching_optimized
    response_headers_policy_id = local.response_policy_security
    compress                   = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# -----------------------------------------------------------------------------
# Alternativa sin CloudFront (CR-002): Lambda web-proxy detrás de HTTP API
# Sirve /, /admin/*, /config.js y /assets/* desde los buckets privados por HTTPS.
# -----------------------------------------------------------------------------
data "archive_file" "web_proxy" {
  count       = var.enable_cloudfront ? 0 : 1
  type        = "zip"
  output_path = "${path.root}/.build/web_proxy.zip"

  source {
    filename = "web_proxy.py"
    content  = <<-PY
      import base64
      import mimetypes
      import os
      import boto3
      from botocore.exceptions import ClientError

      s3 = boto3.client("s3")
      WEB_BUCKET = os.environ["WEB_BUCKET"]
      ASSETS_BUCKET = os.environ["ASSETS_BUCKET"]

      EXTRA_TYPES = {
          ".js": "application/javascript; charset=utf-8",
          ".mjs": "application/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8",
          ".html": "text/html; charset=utf-8",
          ".json": "application/json; charset=utf-8",
          ".webp": "image/webp",
          ".svg": "image/svg+xml",
      }

      def handler(event, context):
          raw_path = (event.get("rawPath") or "/").lstrip("/")
          if not raw_path or raw_path.endswith("/"):
              key = f"{raw_path}index.html"
          elif raw_path == "admin":
              key = "admin/index.html"
          else:
              key = raw_path

          bucket = ASSETS_BUCKET if key.startswith("assets/") else WEB_BUCKET
          try:
              obj = s3.get_object(Bucket=bucket, Key=key)
          except ClientError as exc:
              code = exc.response.get("Error", {}).get("Code", "")
              if code in ("NoSuchKey", "404", "AccessDenied"):
                  return {
                      "statusCode": 404,
                      "headers": {"content-type": "text/plain; charset=utf-8", "strict-transport-security": "max-age=31536000; includeSubDomains"},
                      "body": "Not Found",
                  }
              raise

          body = obj["Body"].read()
          ext = os.path.splitext(key)[1].lower()
          ctype = EXTRA_TYPES.get(ext) or obj.get("ContentType") or mimetypes.guess_type(key)[0] or "application/octet-stream"
          is_text = ctype.startswith("text/") or "javascript" in ctype or "json" in ctype or "xml" in ctype
          headers = {
              "content-type": ctype,
              "cache-control": obj.get("CacheControl") or ("no-cache" if ext in (".html", "") or key == "config.js" else "public, max-age=60"),
              "strict-transport-security": "max-age=31536000; includeSubDomains",
              "x-content-type-options": "nosniff",
          }
          if is_text:
              return {"statusCode": 200, "headers": headers, "body": body.decode("utf-8")}
          return {"statusCode": 200, "headers": headers, "body": base64.b64encode(body).decode("ascii"), "isBase64Encoded": True}
    PY
  }
}

resource "aws_cloudwatch_log_group" "web_proxy" {
  count             = var.enable_cloudfront ? 0 : 1
  name              = "/aws/lambda/${local.prefix}-web-proxy"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "web_proxy" {
  count              = var.enable_cloudfront ? 0 : 1
  name               = "${local.prefix}-lambda-web-proxy"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "web_proxy" {
  count = var.enable_cloudfront ? 0 : 1

  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.web.arn}/*", "${aws_s3_bucket.assets.arn}/*"]
  }

  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.web_proxy[0].arn}:*"]
  }
}

resource "aws_iam_role_policy" "web_proxy" {
  count  = var.enable_cloudfront ? 0 : 1
  name   = "permisos"
  role   = aws_iam_role.web_proxy[0].id
  policy = data.aws_iam_policy_document.web_proxy[0].json
}

resource "aws_lambda_function" "web_proxy" {
  count            = var.enable_cloudfront ? 0 : 1
  function_name    = "${local.prefix}-web-proxy"
  role             = aws_iam_role.web_proxy[0].arn
  handler          = "web_proxy.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = 128
  timeout          = 10
  filename         = data.archive_file.web_proxy[0].output_path
  source_code_hash = data.archive_file.web_proxy[0].output_base64sha256

  environment {
    variables = {
      WEB_BUCKET    = aws_s3_bucket.web.id
      ASSETS_BUCKET = aws_s3_bucket.assets.id
    }
  }

  depends_on = [aws_cloudwatch_log_group.web_proxy, aws_iam_role_policy.web_proxy]
}

resource "aws_apigatewayv2_integration" "web_proxy" {
  count                  = var.enable_cloudfront ? 0 : 1
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.web_proxy[0].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_lambda_permission" "web_proxy" {
  count         = var.enable_cloudfront ? 0 : 1
  statement_id  = "AllowAPIGatewayWebProxy"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.web_proxy[0].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_route" "web_root" {
  count     = var.enable_cloudfront ? 0 : 1
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /"
  target    = "integrations/${aws_apigatewayv2_integration.web_proxy[0].id}"
}

resource "aws_apigatewayv2_route" "web_proxy" {
  count     = var.enable_cloudfront ? 0 : 1
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.web_proxy[0].id}"
}
