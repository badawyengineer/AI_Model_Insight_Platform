# terraform/outputs.tf
#
# None of these expose the raw DB password - `terraform output` is often
# logged/screen-shared without a second thought, and CI logs aren't a
# safe place for it either. Fetch the actual password from
# db_password_secret_arn via the AWS CLI/console, or let
# config_loader.get_db_password() fetch it directly using that ARN.

output "db_host" {
  description = "RDS endpoint hostname. Set as DB_HOST."
  value       = aws_db_instance.this.address
}

output "db_port" {
  description = "RDS port. Set as DB_PORT."
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "Database name. Matches config.yaml's database.dbname."
  value       = aws_db_instance.this.db_name
}

output "db_password_secret_arn" {
  description = "Secrets Manager ARN holding the DB password. Set as DB_PASSWORD_SECRET_ARN."
  value       = aws_secretsmanager_secret.db_password.arn
}

output "mlflow_artifact_bucket" {
  description = "S3 bucket for MLflow artifacts. Use as s3://<this>/... in --default-artifact-root."
  value       = aws_s3_bucket.mlflow_artifacts.id
}

output "mlflow_artifacts_iam_policy_arn" {
  description = "IAM policy ARN granting read/write to the MLflow artifact bucket - attach to whatever compute runs the tracking server."
  value       = aws_iam_policy.mlflow_artifacts_rw.arn
}
