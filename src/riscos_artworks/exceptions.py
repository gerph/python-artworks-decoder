"""Exceptions raised while decoding ArtWorks data."""


class ArtWorksDecodeError(ValueError):
    """Base class for malformed or unsupported input data."""

    def __init__(self, message: str, offset: int | None = None) -> None:
        self.offset = offset
        suffix = "" if offset is None else f" at offset 0x{offset:x}"
        super().__init__(f"{message}{suffix}")


class InvalidHeaderError(ArtWorksDecodeError):
    """The file does not have a valid ArtWorks header."""


class TruncatedDataError(ArtWorksDecodeError):
    """The input ends before a complete value can be decoded."""


class InvalidPointerError(ArtWorksDecodeError):
    """A linked-list pointer violates the format constraints."""


class UnsupportedValueError(ArtWorksDecodeError):
    """A known structure contains a value that cannot be sized safely."""

