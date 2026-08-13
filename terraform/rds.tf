# terraform/rds.tf
#
# A single RDS PostgreSQL instance, replacing the local/Docker `postgres`
# service (Milestone 9) for staging + warehouse data. Uses the default
# VPC for simplicity - a production setup would use a dedicated VPC with
# private subnets instead; see docs/cloud-deployment.md.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.name_prefix}-db-subnet-group"
  subnet_ids = data.aws_subnets.default.ids
  tags       = local.common_tags
}

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "Allows PostgreSQL (5432) from allowed_cidr_blocks only. Empty by default - fails closed."
  vpc_id      = data.aws_vpc.default.id

  dynamic "ingress" {
    for_each = length(var.allowed_cidr_blocks) > 0 ? [1] : []
    content {
      description = "PostgreSQL"
      from_port   = 5432
      to_port     = 5432
      protocol    = "tcp"
      cidr_blocks = var.allowed_cidr_blocks
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# Generated once at apply time, then stored in Secrets Manager (below) -
# never appears in Terraform state as a variable default, and is never
# echoed to stdout via a `terraform output` (see outputs.tf).
resource "random_password" "db" {
  length  = 32
  special = false # simplifies embedding in connection URLs; still 32 alphanumeric chars
}

resource "aws_db_instance" "this" {
  identifier     = "${local.name_prefix}-db"
  engine         = "postgres"
  engine_version = var.db_engine_version

  instance_class    = var.db_instance_class
  allocated_storage = var.db_allocated_storage_gb
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = length(var.allowed_cidr_blocks) > 0

  backup_retention_period = 7
  skip_final_snapshot     = var.environment != "prod"
  deletion_protection     = var.environment == "prod"

  tags = local.common_tags
}

resource "aws_secretsmanager_secret" "db_password" {
  name        = "${local.name_prefix}/db-password"
  description = "PostgreSQL master password for ${aws_db_instance.this.identifier}. Fetched by config_loader.get_db_password() via DB_PASSWORD_SECRET_ARN."
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}
