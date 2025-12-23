import sys
import traceback

from .diagnostics import get_collector
from .main import __version__, parse_args, run


# Python requires a function called `main` in this file
def main(arg_list: None | list[str] = None) -> None:
    """Main entry point for the xl2times tool.

    Returns
    -------
        None.
    """
    args = parse_args(arg_list)

    try:
        run(args)
    except Exception as e:
        collector = get_collector()
        if args.diagnostics_json:
            collector.enable()
            collector.error(
                "INTERNAL_ERROR",
                f"Uncaught exception during processing: {e}",
                context={
                    "exception_type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
            collector.write_json(args.diagnostics_json, __version__)
        raise


if __name__ == "__main__":
    main(sys.argv[1:])
    sys.exit(0)
