from pathlib import Path

from prosapia.core import Tool

from .collect_rfdiffusion3 import collect_rfd3
from .run_rfdiffusion3 import add_run_rfd3_args, build_rfd3_manifest

TOOL = Tool(
    name="rfdiffusion3",
    action="create",
    description="Run RFdiffusion3.",
    default_script=str(Path(__file__).parent / "rfdiffusion3.sh"),
    default_input_column="pdb_path",
    build_manifest_fn=build_rfd3_manifest,
    add_run_args_fn=add_run_rfd3_args,
    collect_fn=collect_rfd3,
)

# ---------------------------------------------------------------------------
# FORK NOTE (2026-10-09)
#
# This is a verbatim fork of the built-in `rfdiffusion3` with ONE change, in
# modal_image.py: `atomworks[ml]<3` is pinned, because rc-foundry 0.2.0 declares
# `atomworks[ml]>=2.1.1` with no upper bound and atomworks 3.0.0 (2026-10-05)
# removed a symbol rfd3 imports at module load. See modal_image.py for the full
# diagnosis.
#
# `name` is deliberately left as "rfdiffusion3" so this SHADOWS the built-in:
# output dir, `rfdiffusion3_status`, `rfdiffusion3_path` and every other column
# stay identical, and no downstream `--input-column` has to change.
#
# Nothing else is modified. Delete this fork once rc-foundry caps atomworks or
# prosapia pins it in the built-in image.
# ---------------------------------------------------------------------------
