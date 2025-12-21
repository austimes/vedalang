#!/usr/bin/env python3
"""Generate the MiniVEDA2 fixture by copying minimal files from DemoS_001.

This fixture uses files from the xl2times DemoS_001 benchmark to ensure
xl2times compatibility. The files are copied (not modified) to serve as
a stable reference for integration testing.
"""

import shutil
from pathlib import Path


def main():
    script_dir = Path(__file__).parent
    out_dir = script_dir / "MiniVEDA2"
    source_dir = script_dir.parent / "xl2times" / "benchmarks" / "xlsx" / "DemoS_001"

    if not source_dir.exists():
        raise FileNotFoundError(
            f"DemoS_001 benchmark not found at {source_dir}. "
            "Ensure xl2times submodule is initialized."
        )

    # Clean and recreate output directory
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir()

    # Copy required files from DemoS_001
    files_to_copy = [
        "SysSettings.xlsx",
        "VT_REG_PRI_V01.xlsx",
    ]

    for filename in files_to_copy:
        src = source_dir / filename
        if src.exists():
            shutil.copy2(src, out_dir / filename)
            print(f"  Copied {filename}")
        else:
            print(f"  Warning: {filename} not found in DemoS_001")

    print(f"\nCreated MiniVEDA2 fixture in {out_dir}")
    print(f"Source: {source_dir}")


if __name__ == "__main__":
    main()
