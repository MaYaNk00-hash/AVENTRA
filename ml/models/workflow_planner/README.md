# Model M4: Workflow Planner

## Overview
Compiles validated business intents into executable Directed Acyclic Graphs (DAGs) conforming to enterprise tool registries, security allowlists, and policy constraints.

## Guarantees
- Emits networkx-validated DAG structures with 0 cycles.
- Enforces human approval gates before executing mutating or financial enterprise actions.
- Prohibits unauthorized tool invocations.

## Verification
```bash
pytest ml/models/workflow_planner/tests/test_workflow_planner.py
```

