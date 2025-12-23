"""Core logic for running TIMES models through GAMS."""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class RunResult:
    """Result of a TIMES model run."""

    success: bool
    case: str
    work_dir: Path
    gams_command: list[str]
    return_code: int
    lst_file: Path | None = None
    gdx_files: list[Path] = field(default_factory=list)
    model_status: str | None = None
    solve_status: str | None = None
    objective: float | None = None
    errors: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""


def find_times_source() -> Path | None:
    """Locate TIMES source directory.

    Checks common locations:
    1. TIMES_SRC environment variable
    2. ~/TIMES_model (common user install)
    3. Subdirectory in workspace
    """
    if env_path := os.environ.get("TIMES_SRC"):
        p = Path(env_path)
        if p.exists():
            return p

    home_times = Path.home() / "TIMES_model"
    if home_times.exists():
        return home_times

    return None


def get_scaffold_dir() -> Path:
    """Get path to the GAMS scaffold directory."""
    return Path(__file__).parent.parent.parent / "xl2times" / "gams_scaffold"


def setup_work_dir(
    dd_dir: Path,
    case: str,
    work_dir: Path | None = None,
    times_src: Path | None = None,
) -> Path:
    """Set up the GAMS working directory with all required files.

    Creates:
      work_dir/
        source/ -> symlink to TIMES source
        model/  -> DD files
        scenarios/ -> (empty, for compatibility)
        runmodel.gms
        scenario.run
        gams.opt
    """
    if work_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        work_dir = Path(tempfile.mkdtemp(prefix=f"veda_run_{case}_{timestamp}_"))
    else:
        work_dir.mkdir(parents=True, exist_ok=True)

    scaffold = get_scaffold_dir()

    source_dir = work_dir / "source"
    if times_src:
        if source_dir.exists():
            source_dir.unlink()
        source_dir.symlink_to(times_src.resolve())
    else:
        source_dir.mkdir(exist_ok=True)

    model_dir = work_dir / "model"
    model_dir.mkdir(exist_ok=True)

    for dd_file in dd_dir.glob("*.dd"):
        shutil.copy(dd_file, model_dir / dd_file.name)

    scenarios_dir = work_dir / "scenarios"
    scenarios_dir.mkdir(exist_ok=True)

    for scaffold_file in ["runmodel.gms", "scenario.run", "gams.opt"]:
        src = scaffold / scaffold_file
        if src.exists():
            shutil.copy(src, work_dir / scaffold_file)

    return work_dir


def parse_lst_file(lst_path: Path) -> dict:
    """Parse GAMS listing file for model/solve status."""
    result = {
        "model_status": None,
        "solve_status": None,
        "objective": None,
        "errors": [],
    }

    if not lst_path.exists():
        return result

    content = lst_path.read_text(errors="replace")

    model_status_match = re.search(r"MODEL STATUS\s*[:=]\s*(\d+)\s+(\w+)?", content)
    if model_status_match:
        result["model_status"] = (
            model_status_match.group(2) or model_status_match.group(1)
        )

    solve_status_match = re.search(r"SOLVER STATUS\s*[:=]\s*(\d+)\s+(\w+)?", content)
    if solve_status_match:
        result["solve_status"] = (
            solve_status_match.group(2) or solve_status_match.group(1)
        )

    obj_match = re.search(r"OBJECTIVE VALUE\s*[:=]?\s*([\d.eE+-]+)", content)
    if obj_match:
        try:
            result["objective"] = float(obj_match.group(1))
        except ValueError:
            pass

    error_lines = re.findall(r"\*{4,}\s*(ERROR.*?)$", content, re.MULTILINE)
    result["errors"] = error_lines[:10]

    return result


def run_times(
    dd_dir: Path,
    case: str = "scenario",
    times_src: Path | None = None,
    gams_binary: str = "gams",
    work_dir: Path | None = None,
    solver: str = "CBC",
    keep_workdir: bool = False,
    verbose: bool = False,
) -> RunResult:
    """Run a TIMES model through GAMS.

    Args:
        dd_dir: Directory containing DD files from xl2times
        case: Case/scenario name (default: "scenario")
        times_src: Path to TIMES source code (defaults to auto-detect)
        gams_binary: GAMS executable (default: "gams")
        work_dir: Working directory (default: create temp dir)
        solver: LP solver to use (default: "CBC")
        keep_workdir: Keep working directory after run
        verbose: Print verbose output

    Returns:
        RunResult with execution details and status
    """
    if times_src is None:
        times_src = find_times_source()
        if times_src is None:
            return RunResult(
                success=False,
                case=case,
                work_dir=Path("."),
                gams_command=[],
                return_code=-1,
                errors=["TIMES source not found. Set TIMES_SRC env var or --times-src"],
            )

    work_path = setup_work_dir(dd_dir, case, work_dir, times_src)

    cmd = [
        gams_binary,
        "runmodel.gms",
        f"--solve_with={solver}",
        f"--run_name={case}",
    ]

    if verbose:
        print(f"Working directory: {work_path}")
        print(f"Running: {' '.join(cmd)}")

    proc = subprocess.run(
        cmd,
        cwd=work_path,
        capture_output=True,
        text=True,
    )

    lst_file = work_path / f"{case}.lst"
    if not lst_file.exists():
        lst_file = next(work_path.glob("*.lst"), None)

    gdx_files = list(work_path.glob("*.gdx"))

    lst_info = parse_lst_file(lst_file) if lst_file else {}

    success = proc.returncode == 0 and lst_info.get("model_status") in (
        None,
        "1",
        "OPTIMAL",
        "2",
        "LOCALLY OPTIMAL",
        "8",
        "INTEGER SOLUTION",
    )

    result = RunResult(
        success=success,
        case=case,
        work_dir=work_path,
        gams_command=cmd,
        return_code=proc.returncode,
        lst_file=lst_file,
        gdx_files=gdx_files,
        model_status=lst_info.get("model_status"),
        solve_status=lst_info.get("solve_status"),
        objective=lst_info.get("objective"),
        errors=lst_info.get("errors", []),
        stdout=proc.stdout,
        stderr=proc.stderr,
    )

    if not keep_workdir and success and work_dir is None:
        shutil.rmtree(work_path, ignore_errors=True)
        result.work_dir = Path("(cleaned up)")

    return result
