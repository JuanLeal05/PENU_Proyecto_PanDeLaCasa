terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Backend parcial: el bucket llega por -backend-config="bucket=<state_bucket>".
  backend "s3" {
    key          = "app/dev/terraform.tfstate"
    region       = "us-east-2"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      project    = "pan-de-la-casa"
      env        = "dev"
      owner      = "juan-pablo"
      managed-by = "terraform"
    }
  }
}

module "app" {
  source = "../../modules/app"

  env                 = "dev"
  lambda_source_dir   = "${path.root}/../../../backend/src"
  alarm_email         = var.alarm_email
  extra_cors_origins  = var.extra_cors_origins
  extra_callback_urls = var.extra_callback_urls
}
