#!/usr/bin/env python3
"""Generate status summary from bd issues for STATUS.md updates.

Usage:
    uv run python tools/sync_status.py

Outputs a markdown snippet showing current open/closed issue counts
that can be used to update STATUS.md.
"""

import subprocess
from datetime import datetime


def run_bd_command(args: list[str]) -> str:
    """Run a bd command and return output."""
    result = subprocess.run(
        ["bd"] + args,
        capture_output=True,
        text=True,
    )
    return result.stdout


def main():
    # Get all issues
    all_issues = run_bd_command(["list", "--all"])
    lines = all_issues.strip().split("\n")

    open_issues = [line for line in lines if " open " in line]
    closed_issues = [line for line in lines if " closed " in line]

    print(f"# VedaLang Status Sync — {datetime.now().strftime('%Y-%m-%d')}")
    print()
    print(f"**Total issues:** {len(lines)}")
    print(f"**Closed:** {len(closed_issues)}")
    print(f"**Open:** {len(open_issues)}")
    print()

    if open_issues:
        print("## Open Issues")
        print()
        print("| Issue | Priority | Type | Description |")
        print("|-------|----------|------|-------------|")
        for line in open_issues:
            parts = line.split(" - ", 1)
            if len(parts) == 2:
                meta, desc = parts
                # Parse: vedalang-xxx [Px] [type] open
                tokens = meta.split()
                issue_id = tokens[0] if tokens else "?"
                priority = tokens[1] if len(tokens) > 1 else "?"
                issue_type = tokens[2] if len(tokens) > 2 else "?"
                print(f"| `{issue_id}` | {priority} | {issue_type} | {desc} |")
        print()

    print("## Recently Closed (last 10)")
    print()
    for line in closed_issues[-10:]:
        parts = line.split(" - ", 1)
        if len(parts) == 2:
            meta, desc = parts
            issue_id = meta.split()[0]
            print(f"- `{issue_id}`: {desc}")

    print()
    print("---")
    print("Copy relevant sections to docs/STATUS.md")


if __name__ == "__main__":
    main()
