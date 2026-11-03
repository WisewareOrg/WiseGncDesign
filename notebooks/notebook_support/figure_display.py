"""Shows a figure inline in a notebook kernel."""

import io
import sys

from matplotlib.figure import Figure

__all__ = ["show"]


def show(figure: Figure) -> None:
    """Displays `figure` as a PNG image when running in an IPython kernel, and does nothing
    elsewhere."""
    if "IPython" not in sys.modules:
        return
    from IPython import get_ipython
    from IPython.display import Image, display

    if get_ipython() is not None:
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=100)
        display(Image(data=buffer.getvalue()))
