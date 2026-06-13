import subprocess
import shlex

def unsafe_run(user_input):
    # Simulating a common bad practice: string interpolation in shell=True
    # (Though most of our repo uses list-based subprocess.run, I want to see if any drift exists)
    try:
        cmd = f"ls {user_input}"
        print(f"Executing: {cmd}")
        subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
    except Exception as e:
        print(f"Error: {e}")

# Malicious input
malicious_input = "; touch /tmp/pwned"
unsafe_run(malicious_input)

import os
if os.path.exists("/tmp/pwned"):
    print("BREACHED: Command Injection successful!")
    os.remove("/tmp/pwned")
else:
    print("SECURE: Command Injection failed.")
