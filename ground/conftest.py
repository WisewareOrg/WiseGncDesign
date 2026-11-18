"""The ground's test mock: one mock component's dictionary, generated from FPP alone.

The component is `fsw/mock/Mock.fpp`, which includes `Extra.fppi` beside it, instanced as `mock`.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

import fsw.mock
from fsw.codegen.fpp_model import Instance
from fsw.mock import edited
from ground.dictionary import Dictionary

_MOCK = Path(fsw.mock.__file__).with_name("Mock.fpp")
"""The mock component's model."""

_INSTANCE = Instance("Mock.mock", "Mock.Mock", 0x1000)
"""The mock's instance."""


@pytest.fixture(scope="session")
def mock_dictionary() -> Dictionary:
    """The mock's dictionary, instanced as `mock` at base ID 0x1000.

    Returns:
        The dictionary.
    """
    return Dictionary.from_component([_MOCK], _INSTANCE)


@pytest.fixture
def render_mock() -> Callable[..., Dictionary]:
    """Renders an edited mock and gives its dictionary.

    Returns:
        A function taking the directory the model and its `Extra.fppi` are written into, then
        `Mock.fpp`'s edits, `extra`, `Extra.fppi`'s edits, and `base_id`, the instance's base ID,
        each edit `(old, new)` as `fsw.mock.edited` applies it, and giving the dictionary
        `from_component` generates.
    """

    def render(
        directory: Path,
        *edits: tuple[str, str],
        extra: tuple[tuple[str, str], ...] = (),
        base_id: int = 0x1000,
    ) -> Dictionary:
        """Writes the edited mock into the directory and generates its dictionary.

        Args:
            directory: where `Mock.fpp` and `Extra.fppi` are written.
            *edits: `Mock.fpp`'s edits.
            extra: `Extra.fppi`'s edits.
            base_id: the instance's base ID.

        Returns:
            The dictionary.
        """
        (directory / "Mock.fpp").write_text(edited(_MOCK.read_text(), *edits))
        (directory / "Extra.fppi").write_text(
            edited(_MOCK.with_name("Extra.fppi").read_text(), *extra)
        )
        return Dictionary.from_component(
            [directory / "Mock.fpp"], _INSTANCE._replace(base_id=base_id)
        )

    return render
