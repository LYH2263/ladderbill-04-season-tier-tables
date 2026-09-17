import os
import tempfile

# Force a throwaway database before any app module is imported, so tests
# never touch the real DATA_DIR (docker sets it to /data).
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="ladderbill-test-")
