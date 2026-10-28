# -*- encoding: utf-8 -*-
"""kfmailbox command line."""
from __future__ import annotations

import argparse
import os

from hio.base import doing

from kfmailbox.mailboxing import setup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="KERI Foundation mailbox service")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve"])
    parser.add_argument("--boot-host", default=os.environ.get("KF_MAILBOX_BOOT_HOST", "127.0.0.1"))
    parser.add_argument("--boot-port", type=int, default=int(os.environ.get("KF_MAILBOX_BOOT_PORT", "6731")))
    parser.add_argument("--host", default=os.environ.get("KF_MAILBOX_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("KF_MAILBOX_PORT", "6732")))
    parser.add_argument("--base", default=os.environ.get("KF_MAILBOX_BASE", ""))
    parser.add_argument("--public-url", default=os.environ.get("KF_MAILBOX_PUBLIC_URL", ""))
    args = parser.parse_args(argv)

    doers = setup(
        bootHost=args.boot_host,
        bootPort=args.boot_port,
        host=args.host,
        port=args.port,
        base=args.base,
        publicUrlValue=args.public_url or None,
    )
    tock = float(os.environ.get("KF_MAILBOX_DOIST_TOCK", "0.03125"))
    doing.Doist(limit=0.0, tock=tock, real=True).do(doers=doers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
