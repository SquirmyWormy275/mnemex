"""MNEMEX CLI entrypoint.

Single command `mnemex` with subcommands per the design doc's CLI surface:
  ingest:        stihl, college, newsletter, image, manual
  discovery:     demo
  review:        review, identity
  output:        export, strathmark-export
  operations:    doctor, migrate, publish, takedown

Voice (inherited from STRATHMARK):
  - Plain text. No emojis. No ANSI color. No banners.
  - Utility language. Status, action, orientation. No marketing voice.
  - Errors name file/path/value involved AND propose the next action.

A regex-based CI test (tests/test_cli_output_style.py) asserts every
command's output matches the no-emoji / no-ANSI / no-banner rules.

Implementation lands incrementally:
  M2 = stihl
  M2.5 = (none - web archive lives in web/, not here)
  M3 = college
  M3.5 = newsletter
  M4 = image
  M4.5 = publish
  M5 = review, identity
  M6 = export, strathmark-export
  M7 = polish, doctor, migrate
"""

from __future__ import annotations

import argparse
import sys

from mnemex import __version__


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Wires up subcommands and dispatches.

    Implementation lands incrementally per milestone. M0 ships only:
      mnemex --version
      mnemex --help
    """
    parser = argparse.ArgumentParser(
        prog="mnemex",
        description="Timbersports historical archive - third leg of the STRATHEX ecosystem.",
        epilog="See `mnemex <command> --help` for command-specific options.",
    )
    parser.add_argument("--version", action="version", version=f"mnemex {__version__}")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="one-line-per-event progress (default for non-tty stdout)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="full debug log to stderr",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    # M0 ships the parser skeleton. Subcommand handlers land at their respective milestones.
    subparsers.add_parser(
        "doctor", help="diagnostic - checks API keys, libreoffice, store consistency"
    )
    subparsers.add_parser(
        "demo", help="run pipeline against bundled fixtures (no API key)"
    )
    subparsers.add_parser("stihl", help="scrape the STIHL official site (M2)")
    subparsers.add_parser(
        "college", help="parse a college conclave Excel scorebook (M3)"
    )
    subparsers.add_parser(
        "newsletter", help="parse an ALA / CANLOG newsletter PDF (M3.5)"
    )
    subparsers.add_parser("image", help="extract from a photographed scoresheet (M4)")
    subparsers.add_parser("manual", help="paste a CSV with the 9-column legacy schema")
    subparsers.add_parser("publish", help="federation historical-backfill flow (M4.5)")
    subparsers.add_parser("review", help="drain the pending queue (M5)")
    subparsers.add_parser(
        "identity", help="merge / split / redact canonical athletes (M5)"
    )
    subparsers.add_parser("export", help="write CSV / JSON / 9-col XLSX (M6)")
    subparsers.add_parser(
        "strathmark-export", help="emit Tier 1 JSONL for STRATHMARK (M6)"
    )
    subparsers.add_parser("migrate", help="upgrade canonical store schema (M7)")
    subparsers.add_parser(
        "takedown", help="federation takedown - drop all rows from a source"
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    # Dispatch lands at each milestone. M0 returns a clear "not yet" message.
    print(
        f"error: `mnemex {args.command}` is not yet implemented in this build",
        file=sys.stderr,
    )
    print(
        f"hint: see docs/MNEMEX-design-2026-05-04.md for milestone status",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
