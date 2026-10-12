"""Modal image for rfdiffusion3 (used by ``--executor modal``).

Checkpoints live on a Volume (``SAPIA_MODAL_VOLUME_RFD3_CKPT``, default
``sapia-rfd3-checkpoints``) mounted at ``/checkpoints``; populate it once with
``foundry install rfd3 --checkpoint-dir /checkpoints`` from a container of this
image. An ``RFD3_CKPT`` override in ``.env`` must then be a path under
``/checkpoints``, since it is read at submit time and used inside the container.
"""

import modal

from prosapia.core.executors.modal import get_named_volume

CHECKPOINT_DIR = "/checkpoints"
RESOURCES = {"gpu": "A10", "cpu": 8, "memory": "32G", "timeout": "04:00:00"}


def image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("git")
        # FORK DIFF vs the built-in: `atomworks<3` is pinned.
        #
        # rc-foundry 0.2.0 (2026-06-05, the newest release) declares
        # `atomworks[ml]>=2.1.1` with NO upper bound. atomworks then released
        # 3.0.0 on 2026-10-05 and 3.0.1 on 2026-10-08, a breaking major that
        # removed `get_inferred_polymer_bonds` from `atomworks.io.utils.bonds`.
        # rfd3.inference.input_parsing still imports that symbol at module load,
        # so any image resolved from 2026-10-05 onward dies with
        #   ImportError: cannot import name 'get_inferred_polymer_bonds'
        # before a single design is sampled -- for EVERY run shape, de novo,
        # binder and partial diffusion alike. Measured 2026-10-09.
        #
        # 2.2.1 (2026-06-08) is the last 2.x and still satisfies rc-foundry's
        # floor. Pinning atomworks rather than rc-foundry keeps us on the
        # newest foundry while excluding only the incompatible major.
        #
        # This is a workaround for an upstream packaging bug. The real fix is an
        # upper bound in rc-foundry, or this pin in the prosapia built-in; when
        # either lands, delete this fork rather than maintaining it.
        .pip_install("rc-foundry[all]", "atomworks[ml]<3")
        .env({"FOUNDRY_CHECKPOINT_DIRS": CHECKPOINT_DIR})
    )


def volumes() -> dict[str, modal.Volume]:
    return {CHECKPOINT_DIR: get_named_volume("SAPIA_MODAL_VOLUME_RFD3_CKPT", "sapia-rfd3-checkpoints")}
