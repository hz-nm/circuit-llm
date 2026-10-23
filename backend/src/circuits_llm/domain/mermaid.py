"""Render a :class:`Circuit` as a Mermaid flowchart (an overview, not a schematic).

Components become shaped nodes, nets become small round nodes, and each edge is
labelled with the pin it uses, so the connectivity is unambiguous.
"""

from __future__ import annotations

import re
from typing import Final

from .catalog import CATALOG, Category
from .circuit import GROUND_NET, Circuit, Component
from .units import format_si

_SHAPES: Final[dict[Category, tuple[str, str]]] = {
    Category.PASSIVE: ("[", "]"),
    Category.SOURCE: ("{{", "}}"),
    Category.SEMICONDUCTOR: ("([", "])"),
    Category.INTEGRATED: ("[/", "\\]"),
}

_CLASS_DEFS: Final = (
    "classDef passive fill:#eef4ff,stroke:#4a6fd8,color:#1b2b5a",
    "classDef source fill:#fff3e6,stroke:#d9822b,color:#5a3410",
    "classDef semiconductor fill:#eefaf1,stroke:#2f9e57,color:#11401f",
    "classDef integrated fill:#f5eefc,stroke:#8a4fd1,color:#3a1a5e",
    "classDef net fill:#ffffff,stroke:#888888,color:#333333",
    "classDef ground fill:#333333,stroke:#333333,color:#ffffff",
)

_UNSAFE_ID: Final = re.compile(r"[^A-Za-z0-9_]")


def _node_id(prefix: str, name: str) -> str:
    return f"{prefix}_{_UNSAFE_ID.sub('_', name)}"


def _escape(text: str) -> str:
    return text.replace('"', "#quot;")


def _escape_pin(pin: str) -> str:
    # Mermaid 11 parses edge labels as markdown, so "+" / "-" would become list items.
    return _escape(pin).replace("+", "#43;").replace("-", "#45;")


def component_summary(component: Component) -> str:
    """Short human-readable value text such as ``10 kΩ`` or ``2N3904``."""
    spec = CATALOG[component.kind]
    parts: list[str] = []
    if component.value is not None and spec.value_unit is not None:
        parts.append(format_si(component.value, spec.value_unit))
    if component.waveform is not None:
        w = component.waveform
        unit = spec.value_unit or ""
        if w.shape == "sine":
            parts.append(f"sine {format_si(w.amplitude, unit)} @ {format_si(w.frequency, 'Hz')}")
        else:
            parts.append(f"pulse {format_si(w.initial, unit)}→{format_si(w.pulsed, unit)}")
    if component.ac_magnitude:
        parts.append(f"AC {component.ac_magnitude:g}")
    model = component.model or spec.default_model
    if model is not None:
        parts.append(model)
    return ", ".join(parts)


def to_mermaid(circuit: Circuit) -> str:
    lines = ["flowchart LR"]
    for component in circuit.components:
        spec = CATALOG[component.kind]
        open_, close = _SHAPES[spec.category]
        summary = component_summary(component)
        label = f"<b>{component.id}</b><br/>{spec.display_name}" + (
            f"<br/>{summary}" if summary else ""
        )
        node = _node_id("C", component.id)
        lines.append(f'    {node}{open_}"{_escape(label)}"{close}')
        lines.append(f"    class {node} {spec.category.value}")

    for net in circuit.nets():
        node = _node_id("N", net)
        if net == GROUND_NET:
            lines.append(f'    {node}(("⏚ {GROUND_NET}"))')
            lines.append(f"    class {node} ground")
        else:
            lines.append(f'    {node}(("{_escape(net)}"))')
            lines.append(f"    class {node} net")

    for component in circuit.components:
        for pin, net in component.pins.items():
            lines.append(
                f'    {_node_id("C", component.id)} ---|"{_escape_pin(pin)}"| {_node_id("N", net)}'
            )

    lines.extend(f"    {definition}" for definition in _CLASS_DEFS)
    return "\n".join(lines) + "\n"
