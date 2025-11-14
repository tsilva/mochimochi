#!/usr/bin/env python3
"""Test if FAISS imports correctly in the installed tool"""

print("Testing FAISS import...")

try:
    import numpy as np
    import faiss
    HAS_FAISS = True
    print(f"✓ FAISS import successful!")
    print(f"  NumPy version: {np.__version__}")
    print(f"  FAISS version: {faiss.__version__}")
    print(f"  HAS_FAISS = {HAS_FAISS}")
except ImportError as e:
    HAS_FAISS = False
    print(f"✗ FAISS import failed!")
    print(f"  ImportError: {e}")
    print(f"  HAS_FAISS = {HAS_FAISS}")
