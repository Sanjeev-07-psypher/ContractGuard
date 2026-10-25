"""Command-line entry point: ``python -m contractguard.cli <command>``."""

from __future__ import annotations

import argparse
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


def _print_summary(report) -> None:
    m = report.meta
    print(
        f"{report.filename}: {m.title or 'untitled'} ({m.contract_type}, {m.contract_type_source})"
    )
    for p in m.parties:
        print(f"  party: {p.name} [{p.alias or '-'}] {p.role}")
    c = report.counts
    print(
        f"  clauses {c['CLAUSES']} | HIGH {c['HIGH']} MEDIUM {c['MEDIUM']} LOW {c['LOW']} | "
        f"missing {c['MISSING']} review {c['NEEDS_REVIEW']} compliant {c['COMPLIANT']}"
    )
    for f in report.findings:
        if f.status in ("NON_COMPLIANT", "MISSING", "NEEDS_REVIEW"):
            print(
                f"  [{f.status} {f.severity}] {f.rule_id} {f.rule_name} @ {f.location or '-'}: "
                f"{f.reason}"
            )
    for w in report.warnings:
        print(f"  warning: {w}")
    print(f"\n{report.disclaimer}")


def _cmd_analyze(args: argparse.Namespace) -> int:
    from contractguard.errors import ContractGuardError
    from contractguard.pipeline import Options, Resources, run

    if not args.file.is_file():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 2
    options = Options(
        contract_type=None if args.contract_type == "auto" else args.contract_type,
        our_org_name=args.our_org_name,
        policy_id=args.policy_id,
        use_llm=not args.no_llm,
    )
    try:
        resources = Resources.load(with_llm=options.use_llm)
        report = run(args.file, options, resources)
    except ContractGuardError as exc:
        print(f"error [{exc.code}]: {exc.message}", file=sys.stderr)
        return 1
    if args.out:
        args.out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"report written to {args.out}")
    _print_summary(report)
    return 0


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
