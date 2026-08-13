# terraform/variables.tf
#
# Milestone 10: Cloud Deployment. See terraform/README.md before running
# anything here - this provisions real, billable AWS resources.

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used to prefix/tag every resource this creates."
  type        = string
  default     = "ai-model-insight"
}

variable "environment" {
  description = "Deployment environment name (e.g. dev, staging, prod) - used in tags and resource naming."
  type        = string
  default     = "dev"
}

variable "db_name" {
  description = "Name of the application's PostgreSQL database (matches config.yaml's database.dbname)."
  type        = string
  default     = "ai_model_insight"
}

variable "db_username" {
  description = "Master username for the RDS instance."
  type        = string
  default     = "postgres"
}

variable "db_instance_class" {
  description = "RDS instance class. db.t4g.micro is Free-Tier eligible for new AWS accounts - still verify current Free Tier terms before applying."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  description = "Allocated storage for RDS, in GB."
  type        = number
  default     = 20
}

variable "db_engine_version" {
  description = "PostgreSQL engine version. Matches the postgres:16 image used in docker-compose.yml (Milestone 9)."
  type        = string
  default     = "16"
}

variable "allowed_cidr_blocks" {
  description = <<-EOT
    CIDR blocks allowed to reach RDS on port 5432. Defaults to nothing
    (empty) so the database is NOT publicly reachable until you
    explicitly add your IP/VPC range - deliberately fails closed rather
    than defaulting to 0.0.0.0/0.
  EOT
  type    = list(string)
  default = []
}

variable "mlflow_artifact_bucket_force_destroy" {
  description = "If true, `terraform destroy` deletes the MLflow artifact S3 bucket even if it still has objects in it. Defaults to false as a safety net against accidentally losing model artifacts."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Extra tags applied to every resource."
  type        = map(string)
  default     = {}
}
