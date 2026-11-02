# Model M8: Enterprise Anomaly Detection

## Overview
Hybrid transaction monitoring engine combining behavioral statistical modeling (Scikit-Learn Isolation Forest) with enterprise financial rule evaluation to identify anomalous dispatches, fraudulent invoices, and policy violations.

## Risk Tiering
- **CRITICAL / HIGH**: Anomaly score $\ge 0.70$ or severe multi-indicator rule violations. Halts automated execution and demands authenticated approval.
- **MEDIUM**: Anomaly score between $0.40$ and $0.70$. Logged with high-visibility audit annotations.
- **LOW**: Normal baseline operations.

## Verification
```bash
pytest ml/models/anomaly_detection/tests/test_anomaly_detection.py
```

