"""CLI for veda_emit_excel."""

import argparse
import sys
from pathlib import Path

import jsonschema

from . import emit_excel, load_tableir


def main():
    parser = argparse.ArgumentParser(
        description="Emit Excel files from TableIR YAML/JSON"
    )
    parser.add_argument("input", type=Path, help="Path to TableIR YAML or JSON file")
    parser.add_argument(
        "--out",
        "-o",
        type=Path,
        required=True,
        help="Output directory for Excel files",
    )
    parser.add_argument(
        "--no-validate", action="store_true", help="Skip schema validation"
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        tableir = load_tableir(args.input)
        created = emit_excel(tableir, args.out, validate=not args.no_validate)

        print(f"Created {len(created)} Excel file(s):")
        for path in created:
            print(f"  {path}")

    except jsonschema.ValidationError as e:
        print(f"Schema validation error: {e.message}", file=sys.stderr)
        print(
            f"  Path: {' -> '.join(str(p) for p in e.absolute_path)}", file=sys.stderr
        )
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
