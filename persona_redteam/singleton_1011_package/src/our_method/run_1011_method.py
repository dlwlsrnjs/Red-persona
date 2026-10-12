"""Run the integrated 1011 method through the production batch runner.

All arguments are forwarded to ``experiments.run_jmir_persona_batch_api``.  This
entry point fixes the protocol to ``1011_method_v1`` and disables the retired
multi-turn convergence suffix so the only conditional recovery is Case A/B.
"""
from __future__ import annotations

import sys

from experiments.run_jmir_persona_batch_api import main as production_main
from our_method.method_1011 import METHOD_PROTOCOL


def main() -> None:
    if "--method-protocol" in sys.argv:
        index = sys.argv.index("--method-protocol")
        if index + 1 >= len(sys.argv) or sys.argv[index + 1] != METHOD_PROTOCOL:
            raise SystemExit(
                "our_method.run_1011_method requires --method-protocol "
                + METHOD_PROTOCOL
            )
    else:
        sys.argv.extend(("--method-protocol", METHOD_PROTOCOL))
    if "--max-goal-convergence-turns" in sys.argv:
        index = sys.argv.index("--max-goal-convergence-turns")
        if index + 1 >= len(sys.argv) or sys.argv[index + 1] != "0":
            raise SystemExit(
                "our_method.run_1011_method requires "
                "--max-goal-convergence-turns 0"
            )
    else:
        sys.argv.extend(("--max-goal-convergence-turns", "0"))
    production_main()


if __name__ == "__main__":
    main()
