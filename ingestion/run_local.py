import json
import logging
import sys

from collectors.bom import collect_bom_fdr
from collectors.cfa import collect_cfa
from collectors.firms import collect_firms
from collectors.dea import collect_dea
from collectors.vicemergency import collect_vicemergency

COLLECTORS = {
    "firms": collect_firms,
    "vicemergency": collect_vicemergency,
    "cfa": collect_cfa,
    "bom": collect_bom_fdr,
    "dea": collect_dea,
}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    names = sys.argv[1:] or list(COLLECTORS)
    unknown = [n for n in names if n not in COLLECTORS]
    if unknown:
        print(f"Unknown collector(s): {unknown}. Choose from {list(COLLECTORS)}")
        return 2

    failed = False
    for name in names:
        try:
            result = COLLECTORS[name]()
            print(f"OK   {name}: {json.dumps(result)}")
        except Exception as exc:
            failed = True
            print(f"FAIL {name}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
