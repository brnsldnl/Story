"""Edge agent giriş noktası.

Kullanım:
    python -m pdks_edge --config /etc/pdks-edge/config.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys

from .agent import EdgeAgent
from .config import EdgeConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdks-edge", description="PDKS terminal agent")
    parser.add_argument("--config", required=True, help="YAML yapılandırma dosyası")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    try:
        config = EdgeConfig.from_file(args.config)
    except (OSError, ValueError) as exc:
        print(f"Yapılandırma okunamadı: {exc}", file=sys.stderr)
        return 2

    EdgeAgent(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
