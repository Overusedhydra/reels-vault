"""reels-vault CLI entry point."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.extract_reel import main

if __name__ == "__main__":
    main()
