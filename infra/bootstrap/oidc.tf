# ---------------------------------------------------------------------------
# Proveedor OIDC de GitHub Actions: sin llaves de AWS en GitHub.
# AWS valida el certificado de token.actions.githubusercontent.com con su
# propia biblioteca de CAs, por eso no se declara thumbprint_list.
# ---------------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  oidc_provider_arn = aws_iam_openid_connect_provider.github.arn

  # Una confianza por rol: cada uno solo lo asume el "sub" indicado.
  oidc_subjects = {
    plan = "repo:${local.github_repo}:pull_request"
    dev  = "repo:${local.github_repo}:environment:dev"
    prod = "repo:${local.github_repo}:environment:prod"
  }
}

data "aws_iam_policy_document" "trust" {
  for_each = local.oidc_subjects

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [each.value]
    }
  }
}
