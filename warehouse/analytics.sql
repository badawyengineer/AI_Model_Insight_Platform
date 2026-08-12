-- =====================================================================
-- analytics.sql
--
-- Milestone 6: Analytical SQL layer on top of the star schema warehouse.
-- Creates performance indexes on FactTrainingRun, then a set of views
-- (one per dashboard requirement) that Power BI will query directly in
-- Milestone 8, rather than querying raw dimension/fact joins.
--
-- Safe to re-run: indexes use IF NOT EXISTS, views use CREATE OR REPLACE.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. INDEXES
-- Foreign keys on the fact table aren't automatically indexed by
-- Postgres (unlike primary keys), so we add them explicitly for the
-- join-heavy queries the views below perform. status and date_key are
-- indexed because nearly every dashboard query filters or groups by them.
-- ---------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_fact_model      ON warehouse.fact_training_run(model_key);
CREATE INDEX IF NOT EXISTS idx_fact_dataset    ON warehouse.fact_training_run(dataset_key);
CREATE INDEX IF NOT EXISTS idx_fact_hardware   ON warehouse.fact_training_run(hardware_key);
CREATE INDEX IF NOT EXISTS idx_fact_framework  ON warehouse.fact_training_run(framework_key);
CREATE INDEX IF NOT EXISTS idx_fact_researcher ON warehouse.fact_training_run(researcher_key);
CREATE INDEX IF NOT EXISTS idx_fact_experiment ON warehouse.fact_training_run(experiment_key);
CREATE INDEX IF NOT EXISTS idx_fact_date       ON warehouse.fact_training_run(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_status     ON warehouse.fact_training_run(status);


-- ---------------------------------------------------------------------
-- 2. vw_executive_kpis
-- Top-level KPI numbers for the dashboard header.
-- GPU utilization is approximated as (sum of training_time_sec across
-- all runs) / (count of distinct hardware profiles * total wall-clock
-- days observed) -- a simplified proxy since we don't track idle time.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW warehouse.vw_executive_kpis AS
SELECT
    ROUND(AVG(accuracy) FILTER (WHERE status = 'success')::numeric, 4)        AS avg_accuracy,
    ROUND(AVG(f1_score) FILTER (WHERE status = 'success')::numeric, 4)        AS avg_f1_score,
    ROUND((SUM(training_time_sec) / 3600.0)::numeric, 2)                     AS total_training_hours,
    ROUND(SUM(energy_consumption_kwh)::numeric, 2)                           AS total_energy_kwh,
    COUNT(*)                                                                  AS total_runs,
    COUNT(*) FILTER (WHERE status = 'failed')                                 AS failed_runs,
    ROUND(
        (COUNT(*) FILTER (WHERE status = 'failed')::numeric
         / NULLIF(COUNT(*), 0)) * 100, 2
    )                                                                         AS failure_rate_pct,
    COUNT(*) FILTER (WHERE status = 'running')                                AS running_runs
FROM warehouse.fact_training_run;


-- ---------------------------------------------------------------------
-- 3. vw_model_leaderboard
-- Ranked model performance, using RANK() window function so ties share
-- a rank (standard leaderboard behavior).
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW warehouse.vw_model_leaderboard AS
SELECT
    m.model_name,
    COUNT(*)                                            AS total_runs,
    COUNT(*) FILTER (WHERE f.status = 'success')          AS successful_runs,
    ROUND(AVG(f.accuracy) FILTER (WHERE f.status = 'success')::numeric, 4)  AS avg_accuracy,
    ROUND(AVG(f.f1_score) FILTER (WHERE f.status = 'success')::numeric, 4)  AS avg_f1_score,
    ROUND(AVG(f.loss) FILTER (WHERE f.status = 'success')::numeric, 4)      AS avg_loss,
    RANK() OVER (
        ORDER BY AVG(f.accuracy) FILTER (WHERE f.status = 'success') DESC
    ) AS accuracy_rank
FROM warehouse.fact_training_run f
JOIN warehouse.dim_model m ON f.model_key = m.model_key
GROUP BY m.model_name;


-- ---------------------------------------------------------------------
-- 4. vw_dataset_comparison
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW warehouse.vw_dataset_comparison AS
SELECT
    d.dataset_name,
    COUNT(*)                                                              AS total_runs,
    ROUND(AVG(f.accuracy) FILTER (WHERE f.status = 'success')::numeric, 4)  AS avg_accuracy,
    ROUND(AVG(f.training_time_sec) FILTER (WHERE f.status = 'success')::numeric, 2) AS avg_training_time_sec,
    ROUND(
        (COUNT(*) FILTER (WHERE f.status = 'failed')::numeric
         / NULLIF(COUNT(*), 0)) * 100, 2
    ) AS failure_rate_pct
FROM warehouse.fact_training_run f
JOIN warehouse.dim_dataset d ON f.dataset_key = d.dataset_key
GROUP BY d.dataset_name;


-- ---------------------------------------------------------------------
-- 5. vw_framework_comparison
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW warehouse.vw_framework_comparison AS
SELECT
    fw.framework,
    fw.optimizer,
    fw.scheduler,
    COUNT(*)                                                              AS total_runs,
    ROUND(AVG(f.accuracy) FILTER (WHERE f.status = 'success')::numeric, 4)  AS avg_accuracy,
    ROUND(AVG(f.training_time_sec) FILTER (WHERE f.status = 'success')::numeric, 2) AS avg_training_time_sec
FROM warehouse.fact_training_run f
JOIN warehouse.dim_framework fw ON f.framework_key = fw.framework_key
GROUP BY fw.framework, fw.optimizer, fw.scheduler;


-- ---------------------------------------------------------------------
-- 6. vw_gpu_performance
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW warehouse.vw_gpu_performance AS
SELECT
    hw.gpu,
    COUNT(*)                                                                    AS total_runs,
    ROUND(AVG(f.training_time_sec) FILTER (WHERE f.status = 'success')::numeric, 2) AS avg_training_time_sec,
    ROUND(AVG(f.energy_consumption_kwh)::numeric, 4)                              AS avg_energy_kwh,
    ROUND(AVG(f.accuracy) FILTER (WHERE f.status = 'success')::numeric, 4)         AS avg_accuracy,
    ROUND(AVG(f.inference_time_ms)::numeric, 3)                                   AS avg_inference_time_ms
FROM warehouse.fact_training_run f
JOIN warehouse.dim_hardware hw ON f.hardware_key = hw.hardware_key
GROUP BY hw.gpu;


-- ---------------------------------------------------------------------
-- 7. vw_hyperparameter_analysis
-- Uses a CTE to bucket the continuous learning_rate column into
-- readable ranges before aggregating, since raw learning rates span
-- multiple orders of magnitude and aren't meaningful to group on directly.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW warehouse.vw_hyperparameter_analysis AS
WITH bucketed AS (
    SELECT
        f.*,
        e.learning_rate,
        e.batch_size,
        e.epochs,
        CASE
            WHEN e.learning_rate < 0.0001 THEN '< 1e-4'
            WHEN e.learning_rate < 0.001  THEN '1e-4 to 1e-3'
            WHEN e.learning_rate < 0.01   THEN '1e-3 to 1e-2'
            WHEN e.learning_rate < 0.1    THEN '1e-2 to 1e-1'
            ELSE '>= 1e-1'
        END AS learning_rate_bucket
    FROM warehouse.fact_training_run f
    JOIN warehouse.dim_experiment e ON f.experiment_key = e.experiment_key
)
SELECT
    learning_rate_bucket,
    batch_size,
    COUNT(*)                                                            AS total_runs,
    ROUND(AVG(accuracy) FILTER (WHERE status = 'success')::numeric, 4)    AS avg_accuracy,
    ROUND(AVG(epochs)::numeric, 1)                                       AS avg_epochs
FROM bucketed
GROUP BY learning_rate_bucket, batch_size
ORDER BY learning_rate_bucket, batch_size;


-- ---------------------------------------------------------------------
-- 8. vw_training_timeline
-- Daily run counts plus a 7-day rolling average accuracy, using a
-- window function over the date-ordered daily aggregates (computed in
-- a CTE first, since window functions can't directly follow GROUP BY
-- in the same SELECT).
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW warehouse.vw_training_timeline AS
WITH daily AS (
    SELECT
        dd.full_date,
        COUNT(*)                                                            AS runs_count,
        AVG(f.accuracy) FILTER (WHERE f.status = 'success')                   AS daily_avg_accuracy
    FROM warehouse.fact_training_run f
    JOIN warehouse.dim_date dd ON f.date_key = dd.date_key
    GROUP BY dd.full_date
)
SELECT
    full_date,
    runs_count,
    ROUND(daily_avg_accuracy::numeric, 4) AS daily_avg_accuracy,
    ROUND(
        AVG(daily_avg_accuracy) OVER (
            ORDER BY full_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )::numeric, 4
    ) AS rolling_7day_avg_accuracy
FROM daily
ORDER BY full_date;


-- ---------------------------------------------------------------------
-- 9. vw_experiment_source_breakdown  (Milestone 7)
-- Compares synthetic (Milestone 2) vs. real MLflow-tracked training
-- runs side by side, so the dashboard can show that this is now a
-- platform with real ML experiments flowing through it, not only
-- generated data. RANK() breaks ties on avg accuracy within a source.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW warehouse.vw_experiment_source_breakdown AS
SELECT
    e.source,
    COUNT(*)                                                                AS total_runs,
    COUNT(*) FILTER (WHERE f.status = 'success')                            AS successful_runs,
    ROUND(AVG(f.accuracy) FILTER (WHERE f.status = 'success')::numeric, 4)  AS avg_accuracy,
    ROUND(AVG(f.training_time_sec)::numeric, 2)                            AS avg_training_time_sec,
    MIN(f.run_timestamp)                                                    AS earliest_run,
    MAX(f.run_timestamp)                                                    AS latest_run,
    RANK() OVER (ORDER BY AVG(f.accuracy) FILTER (WHERE f.status = 'success') DESC) AS accuracy_rank
FROM warehouse.fact_training_run f
JOIN warehouse.dim_experiment e ON f.experiment_key = e.experiment_key
GROUP BY e.source;
