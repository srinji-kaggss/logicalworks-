import os
from pathlib import Path
from lgwks_substrate_io import _iter_text_files

test_dir = Path("/tmp/lfi_test_dir")
test_dir.mkdir(parents=True, exist_ok=True)

# Create a "legit" file
(test_dir / "legit.txt").write_text("legit content")

# Create a malicious symlink pointing outside the directory (e.g. to /etc/passwd)
import tempfile
secret_file = Path(tempfile.gettempdir()) / "secret.txt"
secret_file.write_text("SUPER_SECRET_DATA")

symlink_path = test_dir / "evil.txt"
if symlink_path.exists():
    symlink_path.unlink()
os.symlink(secret_file, symlink_path)

files = _iter_text_files(test_dir, 100)
print(f"Discovered files:")
for f in files:
    print(f" - {f}")

