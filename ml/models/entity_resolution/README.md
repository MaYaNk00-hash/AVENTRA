# Model M1: Enterprise Entity Resolution

## Overview
Enterprise business entity resolution engine built on multi-key blocking and a 16-dimensional LightGBM pairwise scoring model. Resolves ambiguous, noisy vendor and customer records across independent CRM and ERP systems.

## Architecture
- **Blocking**: MultiKeyBlocker with 3-gram name token indexing, numerical address matching, and distinctive address token buckets.
- **Feature Pipeline**: 16 lexical and interaction features including Jaro-Winkler, token sort ratio, token set ratio, address number overlap, and interaction products.
- **Model**: Gradient Boosted Decision Trees (`LGBMClassifier` with 150 trees).
- **Governance**: Emits `HIGH_CONFIDENCE_MATCH` ($p \ge 0.85$) or `HUMAN_REVIEW_REQUIRED` ($0.40 \le p < 0.85$). Never auto-merges without human approval when risk thresholds are met.

## Verification
Run tests with:
```bash
pytest ml/models/entity_resolution/tests/test_entity_resolution.py
```

