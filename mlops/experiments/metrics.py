"""
metrics.py

Macro-averaged precision/recall/F1 computed directly from predicted vs.
true labels. Implemented by hand (rather than pulling in scikit-learn)
since it's a few lines of tensor ops and the project's dependency rule
is "only add dependencies actually required."
"""

from __future__ import annotations

import torch


def macro_precision_recall_f1(
    y_true: torch.Tensor, y_pred: torch.Tensor, num_classes: int
) -> tuple[float, float, float]:
    """
    Args:
        y_true, y_pred: 1D LongTensors of class indices, same length.
        num_classes: total number of classes.

    Returns:
        (macro_precision, macro_recall, macro_f1), each in [0, 1].
    """
    precisions = []
    recalls = []
    for c in range(num_classes):
        true_pos = int(((y_pred == c) & (y_true == c)).sum())
        pred_pos = int((y_pred == c).sum())
        actual_pos = int((y_true == c).sum())

        precision = true_pos / pred_pos if pred_pos > 0 else 0.0
        recall = true_pos / actual_pos if actual_pos > 0 else 0.0
        precisions.append(precision)
        recalls.append(recall)

    macro_precision = sum(precisions) / num_classes
    macro_recall = sum(recalls) / num_classes
    macro_f1 = (
        2 * macro_precision * macro_recall / (macro_precision + macro_recall)
        if (macro_precision + macro_recall) > 0
        else 0.0
    )
    return macro_precision, macro_recall, macro_f1
