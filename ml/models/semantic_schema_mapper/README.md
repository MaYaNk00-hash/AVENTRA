# Model M2: Semantic Schema Mapper

## Overview
Maps incoming, legacy, or multi-tenant database table attributes (such as CRM Account, ERP Vendor, or Invoice fields) to canonical enterprise definitions using character n-gram TF-IDF embeddings, fuzzy lexical alignment, and strict datatype/relationship compatibility constraints.

## Capabilities
- Reranks canonical concepts against source fields based on combined name, description, and sample values.
- Penalizes datatype mismatches (e.g. numeric types mapped to address fields).
- Enforces Human-in-the-Loop governance: scores under $0.75$ trigger approval review flags rather than speculative auto-mapping.

## Tests
```bash
pytest ml/models/semantic_schema_mapper/tests/test_semantic_schema_mapper.py
```

