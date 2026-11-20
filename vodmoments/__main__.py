"""Run vod-moments as a module: python -m vodmoments find stream.srt"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
