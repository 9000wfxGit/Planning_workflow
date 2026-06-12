"""A tiny YAML subset reader/writer for the workflow's structured files.

The project intentionally avoids external dependencies for the MVP. This module
supports the simple mapping/list/scalar YAML shape used by the generated files.
It is not a general-purpose YAML implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


class StructuredYamlError(ValueError):
    """Raised when a workflow YAML file cannot be parsed."""


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    content: str


def load_yaml_file(path: Path) -> Any:
    try:
        return load_yaml_text(path.read_text(encoding="utf-8"), str(path))
    except OSError as exc:
        raise StructuredYamlError(f"Could not read {path}: {exc}") from exc


def write_yaml_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(data), encoding="utf-8")


def load_yaml_text(text: str, source: str = "<string>") -> Any:
    lines = _preprocess(text, source)
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0].indent, source)
    if index != len(lines):
        line = lines[index]
        raise StructuredYamlError(
            f"{source}:{line.number}: unexpected content: {line.content}"
        )
    return value


def dump_yaml(data: Any) -> str:
    return "\n".join(_dump_value(data, 0)) + "\n"


def _preprocess(text: str, source: str) -> list[_Line]:
    processed: list[_Line] = []
    for number, raw_line in enumerate(text.splitlines(), start=1):
        if "\t" in raw_line:
            raise StructuredYamlError(f"{source}:{number}: tabs are not supported")
        without_comments = _strip_comment(raw_line.rstrip())
        if not without_comments.strip():
            continue
        indent = len(without_comments) - len(without_comments.lstrip(" "))
        processed.append(_Line(number, indent, without_comments.lstrip(" ")))
    return processed


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(line):
        if char == "\\" and in_double and not escaped:
            escaped = True
            continue
        if char == '"' and not in_single and not escaped:
            in_double = not in_double
        elif char == "'" and not in_double:
            in_single = not in_single
        elif char == "#" and not in_single and not in_double:
            if index == 0 or line[index - 1].isspace():
                return line[:index].rstrip()
        escaped = False
    return line


def _parse_block(
    lines: list[_Line], index: int, indent: int, source: str
) -> tuple[Any, int]:
    if index >= len(lines):
        return None, index
    line = lines[index]
    if line.indent < indent:
        return None, index
    if line.indent > indent:
        raise StructuredYamlError(
            f"{source}:{line.number}: unexpected indentation"
        )
    if line.content.startswith("- "):
        return _parse_list(lines, index, indent, source)
    return _parse_dict(lines, index, indent, source)


def _parse_dict(
    lines: list[_Line], index: int, indent: int, source: str
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise StructuredYamlError(
                f"{source}:{line.number}: unexpected nested content"
            )
        if line.content.startswith("- "):
            break
        key, raw_value = _split_key_value(line, source)
        index += 1
        if raw_value == "":
            if index < len(lines) and lines[index].indent > indent:
                value, index = _parse_block(lines, index, lines[index].indent, source)
            else:
                value = None
        else:
            value = _parse_scalar(raw_value)
        result[key] = value
    return result, index


def _parse_list(
    lines: list[_Line], index: int, indent: int, source: str
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise StructuredYamlError(
                f"{source}:{line.number}: unexpected nested list content"
            )
        if not line.content.startswith("- "):
            break

        item_text = line.content[2:].strip()
        index += 1
        if item_text == "":
            if index < len(lines) and lines[index].indent > indent:
                item, index = _parse_block(lines, index, lines[index].indent, source)
            else:
                item = None
        elif _looks_like_mapping_item(item_text):
            item, index = _parse_inline_mapping_item(
                item_text, lines, index, indent, source
            )
        else:
            item = _parse_scalar(item_text)
            if index < len(lines) and lines[index].indent > indent:
                nested = lines[index]
                raise StructuredYamlError(
                    f"{source}:{nested.number}: scalar list item cannot have children"
                )
        result.append(item)
    return result, index


def _parse_inline_mapping_item(
    item_text: str,
    lines: list[_Line],
    index: int,
    indent: int,
    source: str,
) -> tuple[dict[str, Any], int]:
    key, raw_value = _split_key_value(
        _Line(lines[index - 1].number, indent, item_text), source
    )
    item: dict[str, Any] = {}
    if raw_value == "":
        if index < len(lines) and lines[index].indent > indent:
            value, index = _parse_block(lines, index, lines[index].indent, source)
        else:
            value = None
    else:
        value = _parse_scalar(raw_value)
    item[key] = value

    if index < len(lines) and lines[index].indent > indent:
        rest, index = _parse_block(lines, index, lines[index].indent, source)
        if not isinstance(rest, dict):
            line = lines[index - 1]
            raise StructuredYamlError(
                f"{source}:{line.number}: list mapping continuation must be a mapping"
            )
        item.update(rest)
    return item, index


def _split_key_value(line: _Line, source: str) -> tuple[str, str]:
    if ":" not in line.content:
        raise StructuredYamlError(
            f"{source}:{line.number}: expected key/value pair"
        )
    key, raw_value = line.content.split(":", 1)
    key = key.strip()
    if not key:
        raise StructuredYamlError(f"{source}:{line.number}: missing key")
    return key, raw_value.strip()


def _looks_like_mapping_item(text: str) -> bool:
    if text.startswith(("'", '"')):
        return False
    if ":" not in text:
        return False
    return bool(text.split(":", 1)[0].strip())


def _parse_scalar(raw_value: str) -> Any:
    if raw_value == "[]":
        return []
    if raw_value == "{}":
        return {}
    lowered = raw_value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if raw_value.startswith('"') and raw_value.endswith('"'):
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise StructuredYamlError(f"invalid quoted string: {raw_value}") from exc
    if raw_value.startswith("'") and raw_value.endswith("'"):
        return raw_value[1:-1].replace("''", "'")
    try:
        return int(raw_value)
    except ValueError:
        return raw_value


def _dump_value(value: Any, indent: int) -> list[str]:
    if isinstance(value, dict):
        return _dump_dict(value, indent)
    if isinstance(value, list):
        return _dump_list(value, indent)
    return [" " * indent + _format_scalar(value)]


def _dump_dict(data: dict[str, Any], indent: int) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in data.items():
        if value == []:
            lines.append(f"{prefix}{key}: []")
            continue
        if value == {}:
            lines.append(f"{prefix}{key}: {{}}")
            continue
        if isinstance(value, (dict, list)):
            lines.append(f"{prefix}{key}:")
            lines.extend(_dump_value(value, indent + 2))
        else:
            lines.append(f"{prefix}{key}: {_format_scalar(value)}")
    return lines


def _dump_list(data: list[Any], indent: int) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for item in data:
        if isinstance(item, dict):
            if not item:
                lines.append(f"{prefix}- {{}}")
                continue
            first = True
            for key, value in item.items():
                item_prefix = f"{prefix}- " if first else f"{prefix}  "
                if isinstance(value, (dict, list)):
                    lines.append(f"{item_prefix}{key}:")
                    lines.extend(_dump_value(value, indent + 4))
                else:
                    lines.append(f"{item_prefix}{key}: {_format_scalar(value)}")
                first = False
        elif isinstance(item, list):
            lines.append(f"{prefix}-")
            lines.extend(_dump_value(item, indent + 2))
        else:
            lines.append(f"{prefix}- {_format_scalar(item)}")
    return lines


def _format_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=True)
