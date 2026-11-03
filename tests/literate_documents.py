"""The repository's literate documents, by the one rule the literate collector
(`tests/algorithms/test_literate_checks.py`) and CI's literate job both use.

- Every module under `algorithms/gnc_algorithms/`, subpackages included, is an algorithm module,
  except the type modules under `interfaces/`.
- A literate module is a module there that has a notebook `notebooks/<its path>.ipynb`. Every
  algorithm module is literate, and no `interfaces/` module is.
- A notebook document is a top-level `notebooks/<name>.py`, paired with `notebooks/<name>.ipynb`.
- Every notebook is `notebooks/**/*.ipynb`, Jupyter checkpoints excluded.

Run as a script, it prints one set per line for CI:
`sources` (every file `jupytext --sync` takes), `modules` (the literate modules' dotted names),
`documents` (the notebook documents' files), and `outputs`, which names every notebook carrying
an output or execution count on stderr and exits 1 when there is any.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "algorithms" / "gnc_algorithms"
NOTEBOOKS = ROOT / "notebooks"
INTERFACES = "interfaces"


def module_paths() -> list[str]:
    """Every module under `gnc_algorithms`, as its path below the package without `.py`."""
    return sorted(
        "/".join(p.relative_to(SOURCES).with_suffix("").parts)
        for p in SOURCES.rglob("*.py")
        if p.name != "__init__.py"
    )


def algorithm_modules() -> list[str]:
    """The modules under `gnc_algorithms` outside `interfaces/`, as paths without `.py`."""
    return [path for path in module_paths() if path.split("/")[0] != INTERFACES]


def literate_modules() -> list[str]:
    """The modules under `gnc_algorithms` that have a notebook, as paths without `.py`."""
    return [path for path in module_paths() if (NOTEBOOKS / f"{path}.ipynb").is_file()]


def notebook_documents() -> list[Path]:
    """The top-level `notebooks/*.py` files."""
    return sorted(NOTEBOOKS.glob("*.py"))


def notebooks() -> list[Path]:
    """Every notebook under `notebooks/`, Jupyter checkpoints excluded."""
    return sorted(p for p in NOTEBOOKS.rglob("*.ipynb") if ".ipynb_checkpoints" not in p.parts)


def notebooks_with_outputs() -> list[Path]:
    """The notebooks holding any cell output or execution count."""
    return [
        p
        for p in notebooks()
        if any(
            cell.get("outputs") or cell.get("execution_count") is not None
            for cell in json.loads(p.read_text())["cells"]
        )
    ]


def main(argv: list[str]) -> int:
    """Prints the requested set, one entry per line; `outputs` names the notebooks carrying output
    on stderr and exits 1 when there is any."""
    (what,) = argv
    if what == "sources":
        lines = [f"algorithms/gnc_algorithms/{p}.py" for p in literate_modules()]
        lines += [str(p.relative_to(ROOT)) for p in notebook_documents()]
    elif what == "modules":
        lines = ["gnc_algorithms." + p.replace("/", ".") for p in literate_modules()]
    elif what == "documents":
        lines = [str(p.relative_to(ROOT)) for p in notebook_documents()]
    elif what == "outputs":
        lines = [str(p.relative_to(ROOT)) for p in notebooks_with_outputs()]
        if lines:
            print("notebooks committed with outputs:", *lines, sep="\n", file=sys.stderr)
        return 1 if lines else 0
    else:
        raise SystemExit(f"unknown set {what!r}: sources, modules, documents or outputs")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
