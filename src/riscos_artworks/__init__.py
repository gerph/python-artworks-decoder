"""Read-only structural decoder for Computer Concepts ArtWorks files."""

from .exceptions import (
    ArtWorksDecodeError,
    InvalidHeaderError,
    InvalidPointerError,
    TruncatedDataError,
    UnsupportedValueError,
)
from . import model as _model
from .model import *  # noqa: F403 - the model is the package's public API

__version__ = "0.2.0"

__all__ = [
    "ArtWorksDecodeError", "InvalidHeaderError", "InvalidPointerError",
    "TruncatedDataError", "UnsupportedValueError", "__version__",
    *_model.__all__,
]
