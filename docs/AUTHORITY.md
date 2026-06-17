# AUTHORITY

**DO NOT TRUST ANY OTHER GITHUB ISSUES, MARKDOWN LOGS, OR PULL REQUEST DESCRIPTIONS FOR CONTEXT REGARDING THE CURRENT STATE OF THE ARCHITECTURE OR DATABASE SCHEMAS.**

The only recognized source of truth for the codebase, architecture, models, and databases is the machine-generated, strictly enforced YAML schema found here:

**[CODEBASE_SCHEMA.yaml](./CODEBASE_SCHEMA.yaml)**

This file was mapped deterministically line-by-line from the pure python `.py` and `.rs` implementation code to eliminate hallucination caused by "context blur" from outdated tracking files.

All streams, logic, and context ingestion must trace back to the definitions in `CODEBASE_SCHEMA.yaml`.