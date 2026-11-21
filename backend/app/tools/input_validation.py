"""Shared validation for all registered tool execution paths."""

from pydantic import ValidationError


PLACEHOLDER_SENTINELS = frozenset({
    "",
    "empty",
    "unknown",
    "none",
    "null",
    "nil",
    "n/a",
    "na",
    "tbd",
    "to be decided",
    "to be provided",
    "not provided",
    "not specified",
    "unspecified",
    "undefined",
    "-",
    "?",
})


def is_placeholder_value(value) -> bool:
    """Identify generic missing-value sentinels without rejecting real names."""
    if not isinstance(value, str):
        return False

    normalized = value.strip().casefold()

    return (
        normalized in PLACEHOLDER_SENTINELS
        or (normalized.startswith("<") and normalized.endswith(">"))
        or (normalized.startswith("[") and normalized.endswith("]"))
    )


def validate_tool_input(tool, raw_params: dict):
    """Validate tool arguments and reject placeholders in required string fields.

    This must run after input bindings have been resolved and before execution
    or user approval. Pydantic remains the authority for the tool's schema.
    """
    if not isinstance(raw_params, dict):
        raise ValueError("Tool arguments must be an object.")

    schema = getattr(tool, "input_schema", None)
    fields = getattr(schema, "model_fields", None)

    if schema is None or fields is None:
        raise TypeError("Registered tool has no valid Pydantic input schema.")

    for name, field in fields.items():
        if not field.is_required() or name not in raw_params:
            continue

        value = raw_params[name]
        if is_placeholder_value(value):
            raise ValueError(
                f"Required parameter '{name}' contains a placeholder value. "
                "A real value must be provided."
            )

    return schema(**raw_params)
