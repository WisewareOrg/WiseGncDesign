"""Throwaway proof that the clean-tree step fails on an un-ignored file, not an ignored one."""

from pathlib import Path

REPOSITORY = Path(__file__).parents[1]


def test_the_suite_writes_one_ignored_and_one_un_ignored_file():
    """Writes `build-artifacts/ci_proof.txt`, which is ignored, and `ci_proof_unignored.txt`."""
    ignored = REPOSITORY / "build-artifacts" / "ci_proof.txt"
    ignored.parent.mkdir(exist_ok=True)
    ignored.write_text("ignored")
    (REPOSITORY / "ci_proof_unignored.txt").write_text("un-ignored")
