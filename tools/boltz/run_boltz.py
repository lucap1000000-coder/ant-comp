"""Per-chain MSA policy for boltz: a real MSA for the target, none for the binder.

Why this exists
---------------
The bundled builder writes the same MSA policy for every entity: ``msa: empty``
everywhere, or (with ``--use-msa-server``) the key omitted everywhere so boltz
searches each one. Neither is right for a binder complex:

* The **de-novo binder** must have ``msa: empty``. No MSA exists for a sequence
  invented an hour ago, a search is meaningless, and ``--use-msa-server`` would
  put an unpublished design on an external server.
* The **natural target** must have one. Denying it an MSA weakens target
  assembly *and* interface confidence, so good designs read as bad ones. This
  is the confound that undermined an earlier campaign here.

Boltz supports the split natively: ``msa:`` is per entity in the input YAML, and
an entity may name a precomputed ``.a3m``. This builder exposes that.

Two flags, both optional:

``--msa-a3m CHAIN=PATH[,CHAIN=PATH...]``
    Point named chains at precomputed alignments already on the runs volume.
    Nothing is searched and nothing leaves Modal. The path must resolve inside
    the task container, so it lives under the runs mount.

``--msa-empty-chains CHAINS``
    Chain mini-language (``A:C``, ``A,D``). These get ``msa: empty`` even when
    ``--use-msa-server`` is on. This is the flag the skill documents.

Precedence per entity: ``--msa-a3m`` wins, then ``--msa-empty-chains``, then the
bundled behaviour. An entity groups several chains when they share a sequence
(homo-oligomer), so its policy is taken from the first chain in the group; a
group whose chains disagree is a configuration error and raises rather than
silently picking one.
"""

from argparse import ArgumentParser
from pathlib import Path
from typing import cast

from prosapia.core import ManifestCtx
from prosapia.tools.boltz.run_boltz import (
    BoltzArgs,
    add_run_boltz_args,
    build_boltz_manifest,
)
from prosapia.utils import expand_chain_spec, group_by_sequence


class BoltzMsaArgs(BoltzArgs):
    msa_a3m: str | None
    msa_empty_chains: str | None


def add_run_boltz_msa_args(parser: ArgumentParser) -> None:
    add_run_boltz_args(parser)
    parser.add_argument(
        "--msa-a3m",
        type=str,
        default=None,
        metavar="CHAIN=PATH[,CHAIN=PATH]",
        help="Precomputed .a3m per chain, e.g. 'A=/runs/msa/t.a3m,B=/runs/msa/t.a3m'. "
        "Paths must resolve inside the task container (i.e. under the runs mount). "
        "Takes precedence over --msa-empty-chains and --use-msa-server.",
    )
    parser.add_argument(
        "--msa-empty-chains",
        type=str,
        default=None,
        help="Chains that get 'msa: empty' even under --use-msa-server. Chain "
        "mini-language: ':' is an inclusive letter range, ',' separates. Use for "
        "the de-novo binder chain.",
    )


def _parse_a3m_map(spec: str | None) -> dict[str, str]:
    if not spec:
        return {}
    out: dict[str, str] = {}
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(
                f"--msa-a3m entry {item!r} is not CHAIN=PATH. "
                "Example: 'A=/runs/msa/target.a3m,B=/runs/msa/target.a3m'"
            )
        ch, path = item.split("=", 1)
        ch = ch.strip()
        if len(ch) != 1:
            raise ValueError(f"--msa-a3m chain {ch!r} must be a single letter")
        out[ch] = path.strip()
    return out


def _entity_msa_line(
    letters: list[str],
    a3m: dict[str, str],
    empty: set[str],
    use_server: bool,
) -> str:
    """The `msa:` line for one entity, or '' to let boltz search it."""
    policies = []
    for ch in letters:
        if ch in a3m:
            policies.append(("a3m", a3m[ch]))
        elif ch in empty:
            policies.append(("empty", None))
        else:
            policies.append(("default", None))
    first = policies[0]
    if any(p != first for p in policies):
        raise ValueError(
            f"chains {''.join(letters)} share a sequence and so form ONE boltz "
            f"entity, but were given different MSA policies: {policies}. "
            "Give them the same policy."
        )
    kind, value = first
    if kind == "a3m":
        return f"      msa: {value}\n"
    if kind == "empty":
        return "      msa: empty\n"
    return "" if use_server else "      msa: empty\n"


def build_boltz_msa_manifest(ctx: ManifestCtx[BoltzMsaArgs]):
    """Delegate to the bundled builder, then rewrite each YAML's msa: lines.

    Rewriting afterwards rather than reimplementing keeps every other part of
    the contract -- sharding, chain maps, templates, the manifest layout --
    exactly as upstream, so this shadow cannot drift from it.
    """
    args = ctx.args
    a3m = _parse_a3m_map(args.msa_a3m)
    empty = (
        set(expand_chain_spec(args.msa_empty_chains))
        if getattr(args, "msa_empty_chains", None)
        else set()
    )

    for ch, p in a3m.items():
        if not str(p).startswith("/"):
            raise ValueError(
                f"--msa-a3m path for chain {ch} must be absolute and resolve inside "
                f"the task container (under the runs mount), got {p!r}"
            )

    rows = build_boltz_manifest(ctx)

    if not a3m and not empty:
        return rows

    yaml_dir = ctx.out_dir / "boltz_inputs"
    n = 0
    for name in ctx.ready.index:
        name = cast(str, name)
        yaml_path = yaml_dir / f"{name}.yml"
        if not yaml_path.is_file():
            continue
        seq_line_to_letters: list[tuple[str, list[str]]] = []
        sequence = str(ctx.ready.at[name, args.input_column])
        from prosapia.utils import build_chain_map

        chain_map = build_chain_map(
            sequence, args.chains, args.positions, ctx.lookup, name
        )
        for letters, seq in group_by_sequence(chain_map):
            seq_line_to_letters.append((seq, list(letters)))

        out_lines: list[str] = []
        idx = 0
        for line in yaml_path.read_text().splitlines(keepends=True):
            if line.strip().startswith("msa:"):
                continue  # drop the bundled policy; re-added after its sequence
            out_lines.append(line)
            if line.strip().startswith("sequence:") and idx < len(seq_line_to_letters):
                letters = seq_line_to_letters[idx][1]
                out_lines.append(
                    _entity_msa_line(letters, a3m, empty, args.use_msa_server)
                )
                idx += 1
        yaml_path.write_text("".join(out_lines))
        n += 1

    print(f"  per-chain MSA policy applied to {n} input YAML(s)")
    if a3m:
        print(f"    a3m: {a3m}")
    if empty:
        print(f"    empty: {sorted(empty)}")
    return rows
