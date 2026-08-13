# Cloud Deployment (Milestone 10)

Moves the staging/warehouse database to managed AWS RDS PostgreSQL and
MLflow's artifact storage to S3, with the DB password stored in AWS
Secrets Manager instead of a local `.env` file.

## What this milestone provisions vs. doesn't

**Provisioned by `terraform/`:**
- RDS PostgreSQL (staging + warehouse data)
- An S3 bucket for MLflow artifacts
- A Secrets Manager secret for the DB password
- An IAM policy granting read/write to that S3 bucket

**Deliberately NOT provisioned:**
- Compute to run the app/Airflow containers (no ECS/Fargate/EC2) — the
  `app` and `airflow-*` images from Milestone 9 are built for this, but
  wiring up a specific compute platform (ECS Fargate, EKS, plain EC2)
  is a real architectural decision with cost/complexity trade-offs that
  belongs in its own follow-up, not bundled into "point the DB at RDS."
- A remote MLflow tracking *server* deployment — the S3 bucket for
  artifacts is provisioned, but you still need to run
  `mlflow server --default-artifact-root s3://...` somewhere reachable
  (see below for the command; where it runs is the same "which compute
  platform" decision as above).
- A cloud-hosted Airflow (e.g. MWAA) — Milestone 8's self-hosted Airflow
  still applies, just pointed at cloud resources.

This keeps the milestone honest about what "cloud deployment" actually
means here: the *data layer* moved to managed services; the *compute
layer* is still something you run yourself (locally, in Docker, or on
whatever compute you choose) but now talking to cloud infrastructure
instead of local containers.

## Step 1 — Provision the infrastructure

See `terraform/README.md` for the full walkthrough and safety notes.
Short version:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit, especially allowed_cidr_blocks
terraform init
terraform plan
terraform apply
```

## Step 2 — Point the app at RDS + Secrets Manager

Set these instead of the local-Postgres env vars used in Milestones 1-9:

```bash
export DB_HOST=$(terraform -chdir=terraform output -raw db_host)
export DB_PORT=$(terraform -chdir=terraform output -raw db_port)
export DB_PASSWORD_SECRET_ARN=$(terraform -chdir=terraform output -raw db_password_secret_arn)
# Do NOT also set DB_PASSWORD - DB_PASSWORD_SECRET_ARN takes priority
# automatically (see config/config_loader.py get_db_password()), but
# leaving a stale DB_PASSWORD around is just confusing.
```

Install the optional cloud dependency:

```bash
pip install -r requirements-cloud.txt
```

Every existing entry point works unchanged from here — `etl.run_etl`,
`database.load_staging`, `warehouse.transform_load`, the
`mlops.pipeline.run_mlops_pipeline` orchestrator, the Airflow DAG (set
the same env vars in whatever runs the Airflow worker) — none of them
know or care whether the password came from Secrets Manager or a plain
env var; that's the whole point of isolating it in `get_db_password()`.

## Step 3 — Point MLflow's artifact storage at S3

Wherever you run the MLflow tracking server (locally, in the `mlflow`
Docker service from Milestone 9, or on whatever compute you choose):

```bash
BUCKET=$(terraform -chdir=terraform output -raw mlflow_artifact_bucket)

mlflow server \
  --backend-store-uri sqlite:////mlflow/mlflow.db \
  --default-artifact-root "s3://${BUCKET}/artifacts" \
  --host 0.0.0.0 --port 5000
```

(The *backend store* — run metadata, params, metrics — can stay local
sqlite or move to RDS too by pointing `--backend-store-uri` at a
`postgresql://` URL using the same RDS instance; a separate database
name/schema is recommended over reusing `ai_model_insight`'s tables.)

The server process needs AWS credentials with the
`mlflow_artifacts_iam_policy_arn` Terraform output attached (an IAM
role if running on AWS compute; an access key pair via the standard
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` env vars otherwise).

## Step 4 — Verify

```bash
python -m database.load_staging
python -m warehouse.transform_load
```

If these succeed against RDS, the connection is working. Check
CloudWatch or `terraform -chdir=terraform output db_host` +
`psql -h <host> -U postgres -d ai_model_insight` directly to confirm
data landed.

## Tearing down

```bash
cd terraform
terraform destroy
```

Empty the S3 bucket first if `mlflow_artifact_bucket_force_destroy` is
`false` (the default) and it still has objects in it.
