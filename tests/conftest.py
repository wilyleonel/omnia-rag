import os
import sys

CORE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "core"))
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)
