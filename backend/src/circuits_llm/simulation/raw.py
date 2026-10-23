"""Parser for ngspice ASCII raw files (``set filetype=ascii`` + ``write``).

One file holds one plot. Layout::

    Title: ...
    Plotname: Transient Analysis
    Flags: real                    (or "complex")
    No. Variables: 3
    No. Points: 21
    Variables:
        0   time    time
        1   v(n1)   voltage
        ...
    Values:
     0  0.000e+00                  (point index, then one value per variable)
        1.234e+00
     1  ...

Complex values are written as ``re,im``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

MAX_RAW_VARIABLES: Final = 10_000
MAX_RAW_POINTS: Final = 1_000_000

_BRANCH_SUFFIX: Final = "#branch"


class RawParseError(ValueError):
    """The raw file is malformed or truncated."""


@dataclass(frozen=True, slots=True)
class RawPlot:
    plotname: str
    is_complex: bool
    names: tuple[str, ...]  # lower-case; "x#branch" is normalised to "i(x)"
    real: tuple[tuple[float, ...], ...]  # one column per variable
    imag: tuple[tuple[float, ...], ...] | None  # complex plots only

    @property
    def points(self) -> int:
        return len(self.real[0]) if self.real else 0

    def index(self, vector: str) -> int | None:
        try:
            return self.names.index(vector.lower())
        except ValueError:
            return None


def normalize_vector_name(raw: str) -> str:
    name = raw.strip().lower()
    if name.endswith(_BRANCH_SUFFIX):
        return f"i({name.removesuffix(_BRANCH_SUFFIX)})"
    return name


def _header_int(headers: dict[str, str], key: str, limit: int) -> int:
    try:
        value = int(headers[key])
    except (KeyError, ValueError) as exc:
        raise RawParseError(f"raw file header '{key}' is missing or not an integer") from exc
    if not 0 <= value <= limit:
        raise RawParseError(f"raw file header '{key}' = {value} is out of range")
    return value


def _split_sections(text: str) -> tuple[dict[str, str], list[str], list[str]]:
    lines = text.splitlines()
    headers: dict[str, str] = {}
    for position, line in enumerate(lines):
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        if key == "variables":
            values_at = next(
                (i for i in range(position + 1, len(lines)) if lines[i].strip() == "Values:"),
                None,
            )
            if values_at is None:
                raise RawParseError("raw file has no 'Values:' section")
            return headers, lines[position + 1 : values_at], lines[values_at + 1 :]
        headers[key] = value.strip()
    raise RawParseError("raw file has no 'Variables:' section")


def _parse_variables(lines: list[str], count: int) -> tuple[str, ...]:
    names: list[str] = []
    for line in lines[:count]:
        fields = line.split()
        if len(fields) < 2:
            raise RawParseError(f"malformed variable line {line.strip()!r}")
        names.append(normalize_vector_name(fields[1]))
    if len(names) != count:
        raise RawParseError(f"expected {count} variables, found {len(names)}")
    return tuple(names)


def _parse_number(token: str) -> tuple[float, float]:
    re_part, _, im_part = token.partition(",")
    try:
        return float(re_part), float(im_part) if im_part else 0.0
    except ValueError as exc:
        raise RawParseError(f"malformed number {token!r}") from exc


def _parse_values(
    lines: list[str], variables: int, points: int
) -> tuple[list[list[float]], list[list[float]]]:
    tokens = " ".join(lines).split()
    stride = variables + 1  # point index + one value per variable
    if len(tokens) < stride * points:
        raise RawParseError(f"raw file is truncated: expected {points} points")
    real: list[list[float]] = [[] for _ in range(variables)]
    imag: list[list[float]] = [[] for _ in range(variables)]
    for point in range(points):
        base = point * stride
        for var in range(variables):
            re_value, im_value = _parse_number(tokens[base + 1 + var])
            real[var].append(re_value)
            imag[var].append(im_value)
    return real, imag


def parse_raw(text: str) -> RawPlot:
    """Parse one ASCII raw plot. Raises :class:`RawParseError` on malformed input."""
    headers, variable_lines, value_lines = _split_sections(text)
    variables = _header_int(headers, "no. variables", MAX_RAW_VARIABLES)
    points = _header_int(headers, "no. points", MAX_RAW_POINTS)
    is_complex = "complex" in headers.get("flags", "").lower()
    names = _parse_variables(variable_lines, variables)
    real, imag = _parse_values(value_lines, variables, points)
    return RawPlot(
        plotname=headers.get("plotname", ""),
        is_complex=is_complex,
        names=names,
        real=tuple(tuple(column) for column in real),
        imag=tuple(tuple(column) for column in imag) if is_complex else None,
    )
