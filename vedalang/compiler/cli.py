"""CLI for VedaLang compiler."""

import argparse
import sys
from pathlib import Path

import jsonschema
import yaml

from .compiler import compile_vedalang_to_tableir, load_vedalang


def main():
    parser = argparse.ArgumentParser(
        prog="vedalang",
        description="VedaLang compiler - compile .veda.yaml to TableIR or Excel",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # compile subcommand
    compile_parser = subparsers.add_parser(
        "compile", help="Compile VedaLang to TableIR/Excel"
    )
    compile_parser.add_argument(
        "input", type=Path, help="Path to VedaLang source file (.veda.yaml)"
    )
    compile_parser.add_argument(
        "--tableir", "-t", type=Path, help="Output TableIR to YAML file"
    )
    compile_parser.add_argument(
        "--out",
        "-o",
        type=Path,
        help="Output directory for Excel files (chains through veda_emit_excel)",
    )
    compile_parser.add_argument(
        "--no-validate", action="store_true", help="Skip schema validation"
    )
    compile_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    if args.command == "compile":
        run_compile(args)


def run_compile(args):
    """Run the compile command."""
    verbose = args.verbose

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if not args.tableir and not args.out:
        print("Error: Must specify --tableir or --out", file=sys.stderr)
        sys.exit(1)

    try:
        if verbose:
            print(f"Loading VedaLang source: {args.input}")
        source = load_vedalang(args.input)

        if verbose:
            print(f"Compiling (validate={not args.no_validate})...")
        tableir = compile_vedalang_to_tableir(source, validate=not args.no_validate)

        if verbose:
            file_count = len(tableir.get("files", []))
            print(f"Compiled to {file_count} TableIR file(s)")

        if args.tableir:
            args.tableir.parent.mkdir(parents=True, exist_ok=True)
            with open(args.tableir, "w") as f:
                yaml.dump(tableir, f, default_flow_style=False, sort_keys=False)
            print(f"Wrote TableIR to {args.tableir}")

        if args.out:
            from tools.veda_emit_excel import emit_excel

            if verbose:
                print(f"Emitting Excel to: {args.out}")
            created = emit_excel(tableir, args.out, validate=False)
            print(f"Created {len(created)} Excel file(s):")
            for path in created:
                print(f"  {path}")

    except jsonschema.ValidationError as e:
        print(f"Validation error: {e.message}", file=sys.stderr)
        print(
            f"  Path: {' -> '.join(str(p) for p in e.absolute_path)}", file=sys.stderr
        )
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
