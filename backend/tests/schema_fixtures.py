"""Generate schema-valid test inputs from the live tool registry."""

import types
from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import BaseModel, TypeAdapter

from app.tools.registry import registry


def _sample_value(annotation, metadata=()):
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Annotated:
        annotation = args[0]
        metadata = tuple(args[1:]) + tuple(metadata)
        origin = get_origin(annotation)
        args = get_args(annotation)

    if origin is Literal:
        candidates = list(args)
    elif origin in (Union, types.UnionType):
        errors = []
        for branch in args:
            if branch is type(None):
                continue
            try:
                return _sample_value(branch)
            except (TypeError, ValueError) as exc:
                errors.append(str(exc))
        raise TypeError(f"No valid union sample for {annotation!r}: {errors}")
    elif isinstance(annotation, type) and issubclass(annotation, Enum):
        candidates = list(annotation)
    elif annotation is str:
        candidates = [
            "schema-valid-fixture",
            "fixture-value",
            "INR",
            date.today().isoformat(),
            "09:00",
            "0,23",
            "https://example.test",
            "test",
            "x",
        ]
    elif annotation is int:
        candidates = [1, 2, 0, -1]
    elif annotation is float:
        candidates = [1.0, 2.5, 0.0]
    elif annotation is bool:
        candidates = [False, True]
    elif annotation is date:
        candidates = [date.today()]
    elif annotation is datetime:
        candidates = [datetime.now(timezone.utc)]
    elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _sample_model(annotation)
    elif origin in (list, tuple, set):
        item_type = args[0] if args else str
        candidates = [[], [_sample_value(item_type)]]
    elif origin is dict:
        candidates = [{}]
    else:
        candidates = [
            "schema-valid-fixture", 1, 1.0, False, [], {}, None
        ]

    target = Annotated[annotation, *metadata] if metadata else annotation
    adapter = TypeAdapter(target)

    for candidate in candidates:
        try:
            return adapter.validate_python(candidate)
        except (TypeError, ValueError):
            continue

    raise TypeError(
        f"Could not generate a valid fixture for annotation {annotation!r}"
    )


def _sample_model(model):
    values = {}
    for name, field in model.model_fields.items():
        if field.is_required():
            values[name] = _sample_value(field.annotation, field.metadata)
    return model(**values)


def valid_required_tool_params(tool_or_name):
    """Build valid required inputs from a registered tool's current schema."""
    tool = (
        registry.get(tool_or_name)
        if isinstance(tool_or_name, str)
        else tool_or_name
    )
    if tool is None:
        raise LookupError(f"Tool not registered: {tool_or_name!r}")

    schema = getattr(tool, "input_schema", None)
    if not isinstance(schema, type) or not issubclass(schema, BaseModel):
        raise TypeError(f"{tool.name} has no Pydantic input schema")

    return _sample_model(schema).model_dump(
        mode="json",
        exclude_unset=True,
    )


def find_schema_tool():
    """Find a registered Pydantic schema suitable for generic test fixtures."""
    tools = sorted(
        getattr(registry, "_tools", {}).values(),
        key=lambda item: item.name,
    )

    for tool in tools:
        schema = getattr(tool, "input_schema", None)
        if not isinstance(schema, type) or not issubclass(schema, BaseModel):
            continue
        try:
            _sample_model(schema)
            return tool
        except (TypeError, ValueError):
            continue

    raise LookupError("No registered tool has a usable Pydantic schema")
