# email_classification

Isolated artifact: `artifacts/model.joblib`; persisted synthetic dataset: `dataset.json`. No original artifacts are modified.

Train: `python -m showcase.models.email_classification.train`

Evaluate saved estimator: `python -m showcase.models.email_classification.evaluation`

Preprocessing and inference delegate to the versioned showcase core. Configuration records feature contracts; seed/version and estimator parameters are fixed in core for reproducibility. Metrics/provenance are in `artifacts/report.json`. Synthetic results do not establish production accuracy. Text test templates are held out entirely; invoice rows are independently generated and split before fitting; anomaly preprocessing fits only normal training rows. No external AI participates.
