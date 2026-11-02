# Model M6: Controlled Adaptation Recommender

## Overview
Monitors enterprise data schemas for semantic and structural drift. Synthesizes migration diffs and impact analyses without ever modifying governance policies or self-authorizing production changes.

## Safety Invariant
The model creates versioned proposals (`PENDING_HUMAN_APPROVAL`). In adherence to enterprise trust principles, no adaptation patch can be applied until an authorized administrator explicitly validates and cryptographically signs the migration.

## Verification
```bash
pytest ml/models/adaptation_recommender/tests/test_adaptation_recommender.py
```

