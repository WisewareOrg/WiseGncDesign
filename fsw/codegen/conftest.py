"""The codegen tests' test mock: a `Cdh.BusConverter` of two roles, read from FPP alone."""

from collections.abc import Callable
from pathlib import Path

import pytest

from fsw.codegen.fpp_model import Model, read
from fsw.mock import edited

MOCK = """\
module Bus {
  struct A { extra: [2] F64, v: [3] F64 }
  port A(msg: A)
  struct B { n: [2] F64 }
  port B(msg: B)
}
module Gnc {
  enum Mode {
    standby
    running
  }
  array Row = [3] F64
  array Mat = [2] Row
  struct AIcd { V: Row }
  port AIcd(reading: AIcd)
  struct BIcd { n: [2] F64 }
  port BIcd(reading: BIcd)
}
module Cdh {
  passive component BusConverter {
    sync input port aIn: Bus.A
    output port aOut: Gnc.AIcd
    sync input port bIn: Bus.B
    output port bOut: Gnc.BIcd
  }
}
"""
"""Two roles, `a` and `b`, each a bus struct's input paired with a GNC struct's output.

Role `a` takes a 3-vector by an array type and another case, and drops `extra`; role `b` an inline
array. `Mode` and `Mat` are there for the edits that seed a refusal."""


@pytest.fixture
def converter_mock(tmp_path: Path) -> Callable[..., Model]:
    """Reads the mock, edited.

    Args:
        tmp_path: where the mock's file is written.

    Returns:
        A function taking each edit `(old, new)`, as `fsw.mock.edited` applies it, and giving the
        edited mock's model.
    """

    def model(*edits: tuple[str, str]) -> Model:
        """The edited mock's model.

        Args:
            *edits: each `(old, new)` replacement.

        Returns:
            The model.
        """
        path = tmp_path / "Mock.fpp"
        path.write_text(edited(MOCK, *edits))
        return read([path])

    return model
