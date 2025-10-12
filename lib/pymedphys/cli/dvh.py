# pymedphys/cli/dvh.py
"""
PyMedPhys DVH — CLI subcommands integrated with the main `pymedphys` CLI.

Subcommands:
  pymedphys dvh presets [--show NAME]
  pymedphys dvh config  --preset NAME [--override K=V ...]
  pymedphys dvh audit   --preset NAME --out PATH [INPUT ...]
  pymedphys dvh inspect-struct --rtstruct RS.dcm --rtdose RD.dcm --structure NAME
                               [--ct CT_DIR] [--endcaps {truncate,half_slice}]
                               [--inclusion {even_odd,winding}]
                               [--single-slice-half-mm MM] [--json-out PATH] [--quiet]

Notes
-----
- Follows the CLI pattern used in PyMedPhys (argparse subparsers, set_defaults(func=...)).
- Avoids any external CLI dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pymedphys._dvh.api import inspect_structure
from pymedphys._dvh.audit import build_audit
from pymedphys._dvh.config import PRESETS, DVHConfig
from pymedphys._dvh.dicom_io import load_study

# ---------- small helpers ---------- #


def _parse_overrides(items: List[str]) -> Dict[str, Any]:
    """Parse K=V pairs with best-effort typing."""
    out: Dict[str, Any] = {}
    for kv in items:
        if "=" not in kv:
            raise SystemExit(f"Invalid key/value '{kv}'. Expected key=value.")
        k, v = kv.split("=", 1)
        v = v.strip()
        if v.lower() in {"true", "false"}:
            out[k] = v.lower() == "true"
        else:
            try:
                if "." in v:
                    out[k] = float(v)
                else:
                    out[k] = int(v)
            except ValueError:
                out[k] = v
    return out


def _gather_paths(maybe_path: Optional[str]) -> Optional[List[Path]]:
    """Expand a path argument to a list of files; accept single file or a folder."""
    if not maybe_path:
        return None
    p = Path(maybe_path)
    if p.is_dir():
        return sorted([q for q in p.iterdir() if q.is_file()])
    if p.is_file():
        return [p]
    raise SystemExit(f"Path not found: {p}")


# ---------- subcommand implementations (accept args [, remaining]) ---------- #


def presets_cli(args: argparse.Namespace, _remaining: List[str] | None = None) -> None:
    if args.show:
        cfg = DVHConfig.from_preset(args.show)
        print(json.dumps(cfg.to_dict(), indent=2))
        return
    print("Available DVH presets:")
    for name in PRESETS:
        print(f"  - {name}")


def config_cli(args: argparse.Namespace, _remaining: List[str] | None = None) -> None:
    cfg = DVHConfig.from_preset(args.preset)
    if args.override:
        cfg = cfg.replace(**_parse_overrides(args.override))
    print(json.dumps(cfg.to_dict(), indent=2))


def audit_cli(args: argparse.Namespace, _remaining: List[str] | None = None) -> None:
    cfg = DVHConfig.from_preset(args.preset)
    if args.override:
        cfg = cfg.replace(**_parse_overrides(args.override))
    extra: Dict[str, Any] = {
        "cli": {
            "subcommand": "audit",
            "preset": cfg.preset,
            "override": args.override or [],
            "argv": sys.argv[1:],
        }
    }
    rec = build_audit(cfg, args.inputs, extra=extra)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rec.to_json() + "\n", encoding="utf-8")
    print(f"Wrote audit JSON → {out}")


def inspect_struct_cli(
    args: argparse.Namespace, _remaining: List[str] | None = None
) -> None:
    """Load DICOM, voxelise ROI (right-prism + end-caps), report stats (and optional JSON)."""
    ct_files = _gather_paths(args.ct)
    study = load_study(
        rtstruct=args.rtstruct,
        rtdose=args.rtdose,
        ct_slices=ct_files,
        include_names=[args.structure] if args.structure else None,
    )
    if args.structure not in study.structures:
        names = ", ".join(sorted(study.structures))
        raise SystemExit(f"Structure '{args.structure}' not found. Available: {names}")

    struct = study.structures[args.structure]

    if not args.quiet:
        warnings.simplefilter("default")

    info = inspect_structure(
        dose=study.dose,
        struct=struct,
        endcaps=args.endcaps,
        inclusion_rule=args.inclusion,
        single_slice_half_mm=args.single_slice_half_mm,
    )

    if not args.json_out or not args.quiet:
        print(f"Structure:  {info['name']}")
        print(f"End-caps:   {info['endcaps']}")
        print(f"Inclusion:  {info['inclusion']}")
        zs = info["z_spacing_mm"]
        print(f"Slices:     {zs['count']}")
        print(
            "z-spacing:  min/median/max = "
            f"{zs['min_mm']:.3f} / {zs['median_mm']:.3f} / {zs['max_mm']:.3f} mm"
        )
        print(f"Volume:     {info['volume_cc']:.3f} cc")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        if not args.quiet:
            print(f"Wrote JSON → {out}")


# ---------- registration into top-level parser ---------- #


def set_up_dvh_cli(
    subparsers: argparse._SubParsersAction,
) -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    dvh_parser = subparsers.add_parser("dvh", help="Dose–Volume Histogram tools")
    dvh_subparsers = dvh_parser.add_subparsers(dest="dvh")

    # presets
    p = dvh_subparsers.add_parser("presets", help="List presets or show one as JSON")
    p.add_argument("--show", metavar="NAME", help="Show JSON for the given preset")
    p.set_defaults(func=presets_cli)

    # config
    c = dvh_subparsers.add_parser("config", help="Show a resolved configuration (JSON)")
    c.add_argument("--preset", required=True, help=f"Preset name: {', '.join(PRESETS)}")
    c.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="K=V",
        help="Override config fields (repeatable), e.g., target_points=200000",
    )
    c.set_defaults(func=config_cli)

    # audit
    a = dvh_subparsers.add_parser(
        "audit", help="Create an audit JSON from inputs (no DVH yet)"
    )
    a.add_argument("--preset", required=True, help=f"Preset name: {', '.join(PRESETS)}")
    a.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="K=V",
        help="Override config fields (repeatable)",
    )
    a.add_argument("--out", required=True, help="Output audit.json path")
    a.add_argument(
        "inputs", nargs="*", help="Files/directories to hash (e.g., RS.dcm RD.dcm CT/)"
    )
    a.set_defaults(func=audit_cli)

    # inspect-struct
    s = dvh_subparsers.add_parser(
        "inspect-struct",
        help="Voxelise ROI (right-prism + end-caps) and report volume/z-spacing warnings",
    )
    s.add_argument("--rtstruct", required=True, help="Path to RTSTRUCT DICOM")
    s.add_argument("--rtdose", required=True, help="Path to RTDOSE DICOM")
    s.add_argument("--ct", help="Path to CT folder (optional)")
    s.add_argument("--structure", required=True, help="ROI name to inspect")
    s.add_argument(
        "--endcaps",
        choices=["truncate", "half_slice"],
        default="truncate",
        help="End-cap policy",
    )
    s.add_argument(
        "--inclusion",
        choices=["even_odd", "winding"],
        default="even_odd",
        help="In-slice inclusion rule",
    )
    s.add_argument(
        "--single-slice-half-mm",
        type=float,
        default=None,
        help="Half-length (mm) to use for a single-plane half-slice case",
    )
    s.add_argument("--json-out", help="Write a JSON report to this path")
    s.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout summary (use with --json-out)",
    )
    s.set_defaults(func=inspect_struct_cli)

    return dvh_parser, dvh_subparsers


def dvh_cli(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Entry hook used by the top-level CLI to register DVH subcommands."""
    dvh_parser, _ = set_up_dvh_cli(subparsers)
    return dvh_parser
