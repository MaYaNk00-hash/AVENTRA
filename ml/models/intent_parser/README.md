# Model M3: Typed Intent Parser

## Overview
Parses unstructured natural language enterprise prompts into strictly typed JSON execution intentions. Enforces distinct read/write boundaries and incorporates automated adversarial prompt injection protection.

## Security Guarantees
- Distinguishes READ queries (non-destructive) from WRITE actions (requiring Human-in-the-Loop authorization).
- User language alone cannot grant write authorization.
- Detects injection attempts and escalates directly to high-risk security violation status.

## Verification
```bash
pytest ml/models/intent_parser/tests/test_intent_parser.py
```

