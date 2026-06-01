"""Prompt serialization helpers for entity catalogs."""

from __future__ import annotations

from typing import Any


def _field_descriptor(field_name: str, meta: dict[str, Any]) -> str:
    bits = [meta.get("type", "unknown")]
    unit = meta.get("unit")
    if unit:
        bits.append(f"unit={unit}")
    values = meta.get("values")
    if values:
        bits.append(f"values={values}")
    agg = meta.get("agg")
    if agg:
        bits.append(f"agg={agg}")
    return f"{field_name} ({', '.join(bits)})"


def entity_catalog_prompt_block(catalogs: list[dict[str, Any]]) -> str:
    """Serialize catalogs into compact context for LLM layout planning."""
    if not catalogs:
        return ""

    lines = ["<entity_catalogs>"]
    for catalog in catalogs:
        connector_id = catalog.get("connector_id", "unknown")
        lines.append(
            f'## Connector "{connector_id}" '
            f'(schema={catalog.get("schema_version","?")}, '
            f'api={catalog.get("api_version","?")}, '
            f'last_audited={catalog.get("last_audited","?")})'
        )
        for entity in catalog.get("entities", []):
            lines.append(f'- entity_id="{entity.get("entity_id", "")}" label="{entity.get("label", "")}"')
            lines.append(f'  tool="{entity.get("tool", "")}"')
            lines.append(f'  description="{entity.get("description", "")}"')
            field_desc = ", ".join(
                _field_descriptor(field_name, field_meta)
                for field_name, field_meta in entity.get("fields", {}).items()
            )
            lines.append(f"  fields: {field_desc}")
            sortable = entity.get("sortable_by")
            if sortable:
                lines.append(f"  sortable_by: {', '.join(sortable)}")
    lines.append("</entity_catalogs>")
    return "\n".join(lines)
