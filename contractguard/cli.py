"""Command-line entry point: ``python -m contractguard.cli <command>``."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from contractguard import __version__
from contractguard.config import get_settings
from contractguard.models import CONTRACT_TYPES

log = logging.getLogger("contractguard")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contractguard",
        description="ContractGuard: AI-assisted contract review flags. Not legal advice.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable DEBUG logging")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    analyze = sub.add_parser("analyze", help="analyze a contract file (PDF or DOCX)")
    analyze.add_argument("file", type=Path, help="path to a .pdf or .docx contract")
    analyze.add_argument(
        "--contract-type",
        choices=["auto", *CONTRACT_TYPES],
        default="auto",
        help="override automatic contract type detection",
    )
    analyze.add_argument("--org", dest="our_org_name", help="our organization's name")
    analyze.add_argument("--policy", dest="policy_id", help="policy id (default from settings)")
    analyze.add_argument("--no-llm", action="store_true", help="use template explanations only")
    analyze.add_argument("-o", "--out", type=Path, help="write the report JSON to this file")

    sub.add_parser("config", help="print the effective settings (secrets hidden)")
    return parser


def _cmd_analyze(args: argparse.Namespace) -> int:
    if not args.file.is_file():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 2
    # The orchestrator (contractguard.pipeline) arrives once Phases 2-7 exist.
    if importlib.util.find_spec("contractguard.pipeline") is None:
        print("error: the analysis pipeline is not implemented yet.", file=sys.stderr)
        return 3
    return 0  # pragma: no cover


def _cmd_config(_: argparse.Namespace) -> int:
    settings = get_settings()
    data = settings.model_dump(mode="json", exclude={"gemini_api_key"})
    data["gemini_api_key_set"] = settings.gemini_api_key is not None
    print(json.dumps(data, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.command == "analyze":
        return _cmd_analyze(args)
    if args.command == "config":
        return _cmd_config(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
