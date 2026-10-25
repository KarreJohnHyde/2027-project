"""MedTwin training pipelines (classification, detection, segmentation).

Every run reads a sample manifest written by scripts/dataset_task_audit.py, keeps
the test split untouched until the final evaluation, and writes its checkpoint
and predictions under artifacts/training/<run_id>/ (git-ignored) with an
evaluation report and model card under docs/ (versioned).
"""
