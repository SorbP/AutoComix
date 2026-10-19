import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from autocomix.__main__ import main

main()
