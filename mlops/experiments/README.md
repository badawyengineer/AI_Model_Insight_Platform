# mlops/experiments/

Config-driven PyTorch training.

- `model.py` — `SimpleCNN`, a small two-conv-block CNN (capacity tunable
  via `base_channels`/`dropout` in a config).
- `data.py` — CIFAR-10 loading via torchvision, with an automatic
  same-shaped `FakeData` fallback if the dataset can't be downloaded
  (offline machine, restricted network egress). `train_subset_size` /
  `val_subset_size` in a config cap dataset size for fast iteration.
- `metrics.py` — macro precision/recall/F1 from predictions (no extra
  dependency beyond torch).
- `train.py` — the entrypoint. Seeds Python/NumPy/PyTorch, trains, and
  logs everything to MLflow (params, per-epoch + final metrics, system
  metadata, artifacts).
- `configs/*.yaml` — one file per experiment: hyperparameters, model
  config, and `random_seed`. Add a new experiment by adding a new YAML
  file here — nothing in `train.py` needs to change.

Run one:

```bash
python -m mlops.experiments.train --config mlops/experiments/configs/exp01_baseline.yaml
```
