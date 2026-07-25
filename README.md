# AI Model Insight Platform

A production-inspired Data Engineering / MLOps portfolio project that monitors, analyzes,
and visualizes metadata generated during AI training experiments — inspired by the internal
analytics platforms used at organizations like OpenAI, Google DeepMind, NVIDIA, Meta AI,
Anthropic, and Hugging Face.

Instead of storing datasets or model weights, this platform stores and analyzes
**experiment metadata**: hyperparameters, hardware utilization, training/inference
performance, and success/failure outcomes.

## Status

🚧 Version 1.0 in progress — Milestone 1 (Project Foundation & Schema Design).

## Version 1.0 Scope

- Synthetic experiment log generator (Faker)
- Python ETL pipeline (extract, validate, clean)
- PostgreSQL staging layer
- Apache Spark transformations
- Star Schema data warehouse
- Analytical SQL (views, indexes, CTEs, window functions)
- Power BI executive dashboard
- Full documentation (architecture, ER diagram, star schema diagram)

## Folder Structure

```
AI_Model_Insight_Platform/
├── docs/            # Architecture, ER, star schema diagrams
├── generator/        # Synthetic experiment data generator
├── etl/               # Extract, validate, clean pipeline
├── database/          # Schemas, staging models, DB access
├── spark/             # Spark transformation jobs
├── warehouse/          # Star schema DDL + load scripts
├── dashboard/          # Power BI assets
├── config/            # config.yaml + config_loader.py
├── tests/              # Unit/integration tests
├── logs/               # Pipeline logs
├── raw_data/           # Raw generated experiment logs
├── clean_data/         # Cleaned data + Parquet exports
├── requirements.txt
└── README.md
```

## Roadmap

This project evolves through six versions, from a data warehouse foundation
to a full Enterprise AI Observability Platform (MLOps tracking, orchestration,
containerization, cloud deployment, streaming analytics, and multi-team
observability). See `docs/roadmap.md` for the full plan.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Database credentials are supplied via environment variable (`DB_PASSWORD`), never
committed to `config.yaml`.
