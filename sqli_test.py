import sqlite3
import os
import json
from pathlib import Path
from lgwks_storage import StorageGate, CausalTape, GlobalFactList

# Setup a test environment
test_dir = Path("/tmp/sqli_test_dir")
test_dir.mkdir(parents=True, exist_ok=True)
gate = StorageGate(test_dir, tenant_id="tenant1")

# Create a malicious CID to test SQLi in lookup
malicious_cid = "' OR 1=1; --"

# Attempt standard lookup
print("Attempting lookup with malicious CID...")
try:
    result = gate.fact_list.lookup(malicious_cid)
    print(f"Lookup succeeded, result: {result}")
except Exception as e:
    print(f"Lookup failed: {e}")

# Attempt to write with a malicious CID
print("\nAttempting to ingest with malicious CID...")
try:
    gate.ingest_fact(malicious_cid, "test content", "text", "test_cap")
    print("Ingest succeeded.")
except Exception as e:
    print(f"Ingest failed: {e}")

# Verify what was actually written
conn = sqlite3.connect(test_dir / "global_fact_list.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT fact_hash, fact_text FROM global_facts").fetchall()
print("\nContents of global_facts table:")
for row in rows:
    print(dict(row))

# Verify Causal Tape
conn2 = sqlite3.connect(test_dir / "causal_tape.db")
conn2.row_factory = sqlite3.Row
tape_rows = conn2.execute("SELECT fact_cid, capability_id FROM tape").fetchall()
print("\nContents of tape table:")
for row in tape_rows:
    print(dict(row))

