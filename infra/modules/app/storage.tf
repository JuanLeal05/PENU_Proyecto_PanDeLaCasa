locals {
  buckets = {
    web    = local.web_bucket_name
    assets = local.assets_bucket_name
  }
}

resource "aws_s3_bucket" "web" {
  bucket        = local.web_bucket_name
  force_destroy = true # proyecto académico: el curso pide eliminar todo al final
}

resource "aws_s3_bucket" "assets" {
  bucket        = local.assets_bucket_name
  force_destroy = true
}

locals {
  bucket_ids = {
    web    = aws_s3_bucket.web.id
    assets = aws_s3_bucket.assets.id
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = local.bucket_ids

  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = local.bucket_ids

  bucket = each.value

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = local.bucket_ids

  bucket = each.value

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.bucket_ids

  bucket = each.value

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# FinOps: las versiones no actuales se borran a los 30 días.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = local.bucket_ids

  bucket = each.value

  rule {
    id     = "expirar-versiones-no-actuales"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.this]
}

# El admin sube imágenes con PUT a una URL prefirmada desde su navegador.
resource "aws_s3_bucket_cors_configuration" "assets" {
  bucket = aws_s3_bucket.assets.id

  cors_rule {
    allowed_methods = ["PUT"]
    allowed_origins = local.cors_origins
    allowed_headers = ["content-type"]
    max_age_seconds = 3600
  }
}

# Solo CloudFront (OAC) lee los buckets.
data "aws_iam_policy_document" "bucket_read" {
  for_each = local.bucket_ids

  statement {
    sid       = "LecturaSoloCloudFront"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${each.value}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.main.arn]
    }
  }

  statement {
    sid       = "DenegarSinTLS"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = ["arn:aws:s3:::${each.value}", "arn:aws:s3:::${each.value}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  for_each = local.bucket_ids

  bucket     = each.value
  policy     = data.aws_iam_policy_document.bucket_read[each.key].json
  depends_on = [aws_s3_bucket_public_access_block.this]
}
