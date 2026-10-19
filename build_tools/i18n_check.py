"""Lists all tr("...") texts in autocomix and checks the translations in autocomix/lang/*.json.

  python build_tools/i18n_check.py            # report: missing, superfluous and broken {placeholders}
  python build_tools/i18n_check.py --keys     # write all texts (one per line, JSON) to stdout
"""
import ast
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PH = re.compile(r"\{[^{}]*\}")


def keys():
    out = {}
    for f in sorted((ROOT / "autocomix").glob("*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "tr" and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                out.setdefault(n.args[0].value, f"{f.name}:{n.lineno}")
    return out


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ks = keys()
    if "--keys" in sys.argv:
        for k in ks:
            print(json.dumps(k, ensure_ascii=False))
        return 0
    bad = 0
    for f in sorted((ROOT / "autocomix" / "lang").glob("*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        missing = [k for k in ks if not t.get(k)]
        extra = [k for k in t if k not in ks]
        wrong = [k for k in t if k in ks and sorted(PH.findall(k)) != sorted(PH.findall(t[k]))]
        amp = [k for k in t if k in ks and ("&" in k) != ("&" in t[k])]
        print(f"{f.stem}: {len(t)} texter, saknas {len(missing)}, överflödiga {len(extra)}, "
              f"fel platshållare {len(wrong)}, fel &-snabbtangent {len(amp)}")
        for k in missing[:5] + wrong + amp:
            print("   ", k)
        bad += len(missing) + len(wrong) + len(amp)
    print(f"{len(ks)} texter i koden")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
