# terraform/s3.tf
#
# S3 bucket for MLflow artifacts (model checkpoints, config copies,
# metrics JSON, training curves - see mlops/experiments/train.py),
# replacing the local `mlflow_data` Docker volume from Milestone 9.
# A remote MLflow tracking server would be started with:
#   mlflow server --default-artifact-root s3://<this bucket>/... --backend-store-uri <RDS/other DB>
# See docs/cloud-deployment.md for the full command.

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "mlflow_artifacts" {
  bucket        = "${local.name_prefix}-mlflow-artifacts-${random_id.bucket_suffix.hex}"
  force_destroy = var.mlflow_artifact_bucket_force_destroy

  tags = local.common_tags
}

resource "aws_s3_bucket_versioning" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# IAM policy an MLflow tracking server (or the app/Airflow containers,
# if they write artifacts directly) needs to read/write this bucket.
# Attach this to whatever compute runs the tracking server - this
# module only defines the policy document, not the compute itself.
data "aws_iam_policy_document" "mlflow_artifacts_rw" {
  statement {
    sid    = "MlflowArtifactsReadWrite"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.mlflow_artifacts.arn,
      "${aws_s3_bucket.mlflow_artifacts.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "mlflow_artifacts_rw" {
  name        = "${local.name_prefix}-mlflow-artifacts-rw"
  description = "Read/write access to the MLflow artifact S3 bucket."
  policy      = data.aws_iam_policy_document.mlflow_artifacts_rw.json
  tags        = local.common_tags
}
