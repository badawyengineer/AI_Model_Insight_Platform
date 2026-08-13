# terraform/ — Milestone 10: Cloud Deployment (infrastructure)

Provisions the AWS resources this project's cloud deployment needs:

- **RDS PostgreSQL** (`rds.tf`) — replaces the local/Docker `postgres`
  service from Milestone 9 for staging + warehouse data
- **An S3 bucket** (`s3.tf`) — replaces the local `mlflow_data` Docker
  volume for MLflow artifacts (checkpoints, configs, metrics, curves)
- **A Secrets Manager secret** holding the generated DB password —
  consumed directly by `config_loader.get_db_password()` via
  `DB_PASSWORD_SECRET_ARN`, so the real password is never written to a
  `.tfvars` file, `terraform output`, or any log

**This does NOT provision compute** to run the app/Airflow containers
(no ECS/EC2/Fargate) or a remote MLflow tracking server — see
`docs/cloud-deployment.md` for why, and what a next iteration would add.

## ⚠️ Before you run anything here

- This creates **real, billable AWS resources**. `db.t4g.micro` is
  Free-Tier eligible for new accounts as of this writing, but verify
  current AWS Free Tier terms yourself before applying — they change.
- `allowed_cidr_blocks` defaults to `[]` (empty) on purpose: RDS is
  **not publicly reachable** until you explicitly add your IP/CIDR.
  Never set it to `["0.0.0.0/0"]` outside of throwaway testing.
- Requires AWS credentials configured locally (`aws configure`, or an
  `AWS_PROFILE`/`AWS_ACCESS_KEY_ID`+`AWS_SECRET_ACCESS_KEY` pair) with
  permission to create RDS, S3, Secrets Manager, and IAM policy
  resources.

## Usage

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit values, especially allowed_cidr_blocks
terraform init
terraform plan     # review every resource before creating anything
terraform apply
```

Get the values you need for the app/Docker/Airflow environment:

```bash
terraform output db_host
terraform output db_port
terraform output db_password_secret_arn
terraform output mlflow_artifact_bucket
```

Then set, wherever the app/Airflow environment runs:

```bash
export DB_HOST=$(terraform output -raw db_host)
export DB_PORT=$(terraform output -raw db_port)
export DB_PASSWORD_SECRET_ARN=$(terraform output -raw db_password_secret_arn)
# DB_PASSWORD itself is never needed - get_db_password() fetches it
# from Secrets Manager automatically once DB_PASSWORD_SECRET_ARN is set.
```

See `docs/cloud-deployment.md` for the full walkthrough, including
pointing a remote MLflow tracking server at the new S3 bucket.

## Tearing down

```bash
terraform destroy
```

`mlflow_artifact_bucket_force_destroy` defaults to `false`, so destroy
will fail (safely) if the artifact bucket still has objects in it —
empty it first if you actually want to delete everything.

## What wasn't validated in this sandbox

The Terraform CLI itself isn't installable in the environment this was
developed in (no `terraform` package in the default apt repos, and
HashiCorp's own release site isn't reachable through this sandbox's
network allowlist). What *was* verified:

- Every `.tf` file parses as syntactically valid HCL (via `python-hcl2`)
- The resource graph, variable references, and IAM policy document were
  reviewed by hand against the AWS provider's current schema

Run `terraform validate` and `terraform plan` yourself before applying —
standard practice for any Terraform change, sandbox or not.
