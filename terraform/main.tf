# terraform/main.tf
#
# Milestone 10: Cloud Deployment. Provisions:
#   - RDS PostgreSQL (replaces the local/Docker `postgres` service for
#     staging + warehouse data)
#   - An S3 bucket for MLflow artifacts (replaces the local `mlflow_data`
#     volume from Milestone 9)
#   - A Secrets Manager secret for the DB password, consumed by
#     config_loader.get_db_password() via DB_PASSWORD_SECRET_ARN
#   - A security group that fails closed: RDS is not publicly reachable
#     until allowed_cidr_blocks is explicitly set
#
# This does NOT provision a remote MLflow tracking server or compute to
# run the app/Airflow containers (ECS, EC2, etc.) - see
# docs/cloud-deployment.md for why, and what a next iteration would add.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Milestone   = "10-cloud-deployment"
    },
    var.tags,
  )
}
