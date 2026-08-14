# streaming/ + monitoring/ — Milestone 11: Streaming & Advanced Monitoring

Real-time prediction-log ingestion, drift detection, and alerting on top
of the batch pipeline built in Milestones 1-10.

## Why Redis Streams, not Kafka

The roadmap called for "Kafka or similar." Redis Streams was chosen
deliberately: it's genuinely lightweight to run for a project this size
(`apt install redis-server` — no ZooKeeper/KRaft cluster, no JVM), while
still providing the core properties this milestone needs — an
append-only, replayable log with consumer-group semantics
(`XREADGROUP`/`XACK`, at-least-once delivery, redelivery of
unacknowledged entries). Kafka is the right call at a scale this
project doesn't operate at. `streaming/producer.py` and
`streaming/consumer.py` are written the same way either technology
would be used, so swapping in `kafka-python` later would only touch
those two files — nothing downstream (`streaming/schemas.py`,
`database/monitoring_models.py`, `monitoring/`) would need to change.

## Pipeline

```
(simulated) model serving
        |
        v
streaming/producer.py  --XADD-->  Redis stream "prediction_events"
                                          |
                                          v
                          streaming/consumer.py (XREADGROUP + XACK)
                                          |
                                          v
                     database.monitoring_models.PredictionEvent
                          (monitoring.prediction_events table)
                                          |
                                          v
                       monitoring/drift_detection.py (PSI)
                                          |
                                          v
                          monitoring/alerting.py (log + webhook)
```

Orchestrated on a 15-minute schedule by
`orchestration/dags/monitoring_pipeline_dag.py` — deliberately a
separate DAG from the daily training/warehouse pipeline (Milestone 8),
since real-time monitoring shouldn't wait for, or be blocked by, the
next daily batch run.

## Quick start

```bash
# Terminal 1: start Redis (if not already running)
redis-server &

# Publish 400 simulated prediction events, with a distribution shift
# injected partway through (for exercising drift detection)
python -m streaming.producer --simulate 400 --drift-after 200

# Consume everything currently on the stream into PostgreSQL
python -m streaming.consumer --once

# Check a model for drift (also sends an alert if PSI exceeds the
# threshold in config.yaml's monitoring.psi_drift_threshold)
python -m monitoring.drift_detection --model-name fraud-detector --model-version v3

# Run continuously instead (Ctrl+C to stop):
python -m streaming.consumer
```

Set `ALERT_WEBHOOK_URL` (a Slack incoming-webhook URL, or any endpoint
that accepts a `{"text": "..."}` POST body) to also deliver alerts
there — they're always logged either way.

## Why PSI, and why the default window is 200 events

Population Stability Index (PSI) is the standard metric for this in
industry MLOps/model-risk practice — easy to threshold consistently
across features/models, no distributional assumption required. Common
bands: `<0.1` no significant shift, `0.1-0.25` moderate (investigate),
`>0.25` significant. This project defaults `psi_drift_threshold` to
`0.25`.

**Important, verified during development:** PSI is a bin-count
statistic, so it's noisy — and can false-positive above the threshold —
at small sample sizes. Two draws from the *identical* distribution at
`n=30` with a naive fixed bin count regularly produced PSI values above
1.0 (would have falsely fired as "significant drift" on stable data).
`monitoring/drift_detection.py`'s `compute_psi()` caps the bin count
relative to sample size (~20 points/bin minimum) as a safety net, and
`config.yaml`'s `min_events_for_drift_check` defaults to `200` — the
smallest window size that kept the false-positive rate reliably under
threshold across repeated trials during testing. See that function's
docstring for the exact numbers.

## Tests

```bash
pytest tests/test_drift_detection.py tests/test_alerting.py -v          # no Redis/Postgres needed
pytest tests/test_streaming_integration.py -v                            # needs real Redis + PostgreSQL (skips gracefully otherwise)
pytest tests/test_monitoring_dag.py -v                                   # needs apache-airflow installed (skips gracefully otherwise)
```
