# ---------------------------------------------------------------------------
# Rol de plan (PRs): solo lectura. Corre con `terraform plan -lock=false`.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "plan" {
  name                 = "pdc-github-plan"
  assume_role_policy   = data.aws_iam_policy_document.trust["plan"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "plan_state" {
  statement {
    sid       = "LeerState"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
  }

  statement {
    sid       = "ListarState"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
  }
}

resource "aws_iam_role_policy" "plan_state" {
  name   = "lectura-state"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.plan_state.json
}

# ---------------------------------------------------------------------------
# Roles de despliegue (dev y prod)
#
# DECISIÓN (ADR-006): un rol con mínimo privilegio acción por acción es muy
# caro de mantener en 3 días. Se usa PowerUserAccess (todo excepto IAM y
# Organizations) + una política IAM acotada a los roles `pdc-<env>-*`.
# Mitigaciones: el rol de prod solo lo asume el environment `prod` (con
# aprobación manual y solo desde `main`), y se niega el acceso al state de
# otros ambientes y del bootstrap.
# ---------------------------------------------------------------------------
locals {
  deploy_envs = toset(["dev", "prod"])
}

resource "aws_iam_role" "deploy" {
  for_each = local.deploy_envs

  name                 = "pdc-github-${each.key}"
  assume_role_policy   = data.aws_iam_policy_document.trust[each.key].json
  max_session_duration = 3600

  tags = {
    env = each.key
  }
}

resource "aws_iam_role_policy_attachment" "deploy_poweruser" {
  for_each = local.deploy_envs

  role       = aws_iam_role.deploy[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

data "aws_iam_policy_document" "deploy" {
  for_each = local.deploy_envs

  # IAM acotado a los roles de la aplicación de este ambiente.
  statement {
    sid = "IamRolesDelAmbiente"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:PutRolePolicy",
      "iam:GetRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/pdc-${each.key}-*"]
  }

  statement {
    sid       = "PassRoleSoloLambdaYScheduler"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/pdc-${each.key}-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "scheduler.amazonaws.com"]
    }
  }

  # Acceso al bucket de state (y a su lockfile) solo bajo app/<env>/.
  statement {
    sid       = "StateDelAmbiente"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/app/${each.key}/*"]
  }

  statement {
    sid       = "ListarState"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
  }

  # PowerUserAccess incluye s3:*; este Deny explícito protege el state del
  # bootstrap y el del otro ambiente.
  statement {
    sid     = "DenegarStateAjeno"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      "${aws_s3_bucket.state.arn}/bootstrap/*",
      "${aws_s3_bucket.state.arn}/app/${each.key == "dev" ? "prod" : "dev"}/*",
    ]
  }
}

resource "aws_iam_role_policy" "deploy" {
  for_each = local.deploy_envs

  name   = "despliegue-${each.key}"
  role   = aws_iam_role.deploy[each.key].id
  policy = data.aws_iam_policy_document.deploy[each.key].json
}
