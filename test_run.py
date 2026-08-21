import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import sys
sys.path.append('src/core')
from indexer import OmniaIndexer
print("Starting indexer test...", flush=True)

class DebugIndexer(OmniaIndexer):
    def index_file(self, file_path, force=False):
        print(f"Processing: {file_path}", flush=True)
        try:
            result = super().index_file(file_path, force=force)
            print(f"SUCCESS: {file_path}", flush=True)
            return result
        except Exception as e:
            print(f"FAILED {file_path}: {e}", flush=True)
            raise

indexer = DebugIndexer()
print("Indexer initialized.", flush=True)
indexer.scan_all()
print("Done", flush=True)
