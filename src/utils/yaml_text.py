"""Text-level YAML helpers for preserving comments and layout on write."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_YAML_KEY_RE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_-]+):(?P<tail>.*)$")


def patch_yaml_values(path: Path, patch: Mapping[str, Any]) -> None:
    """Patch only supplied mapping values in a YAML file without reformatting it."""

    if not patch:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    newline = _detect_newline(text)
    lines = text.splitlines(keepends=True)
    _apply_mapping_patch(lines, patch, 0, len(lines), 0, newline)
    _write_text(path, "".join(lines))


def render_yaml_mapping(mapping: Mapping[str, Any]) -> str:
    """Render a small YAML mapping without using a YAML formatter."""

    lines = _render_mapping_lines(mapping, 0, "\n")
    return "".join(lines).rstrip("\n")


def _detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        file.write(text)


def _apply_mapping_patch(
    lines: list[str],
    patch: Mapping[str, Any],
    start: int,
    end: int,
    indent: int,
    newline: str,
) -> int:
    current_end = end
    for raw_key, value in patch.items():
        key = str(raw_key)
        index = _find_key_line(lines, start, current_end, indent, key)
        if isinstance(value, Mapping):
            if not value:
                continue
            if index is None:
                rendered = _render_mapping_entry(key, value, indent, newline)
                _insert_lines(lines, current_end, rendered, newline)
                current_end += len(rendered)
                continue

            block_end = _find_block_end(lines, index, current_end, indent)
            new_end = _apply_mapping_patch(
                lines,
                value,
                index + 1,
                block_end,
                indent + 2,
                newline,
            )
            current_end += new_end - block_end
            continue

        if index is None:
            rendered = [f"{' ' * indent}{key}: {_format_scalar(value)}{newline}"]
            _insert_lines(lines, current_end, rendered, newline)
            current_end += 1
        else:
            lines[index] = _replace_scalar_line(lines[index], value)
    return current_end


def _find_key_line(
    lines: list[str],
    start: int,
    end: int,
    indent: int,
    key: str,
) -> int | None:
    for index in range(start, end):
        match = _YAML_KEY_RE.match(_strip_eol(lines[index]))
        if not match:
            continue
        if len(match.group("indent")) == indent and match.group("key") == key:
            return index
    return None


def _find_block_end(lines: list[str], key_index: int, end: int, indent: int) -> int:
    for index in range(key_index + 1, end):
        raw = _strip_eol(lines[index])
        stripped = raw.strip()
        if not stripped:
            continue
        current_indent = len(raw) - len(raw.lstrip(" "))
        if stripped.startswith("#") and current_indent <= indent:
            return index
        if current_indent <= indent:
            return index
    return end


def _insert_lines(
    lines: list[str],
    index: int,
    rendered: list[str],
    newline: str,
) -> None:
    if index > 0 and not _has_eol(lines[index - 1]):
        lines[index - 1] = f"{lines[index - 1]}{newline}"
    lines[index:index] = rendered


def _render_mapping_entry(
    key: str,
    value: Mapping[str, Any],
    indent: int,
    newline: str,
) -> list[str]:
    lines = [f"{' ' * indent}{key}:{newline}"]
    lines.extend(_render_mapping_lines(value, indent + 2, newline))
    return lines


def _render_mapping_lines(
    mapping: Mapping[str, Any],
    indent: int,
    newline: str,
) -> list[str]:
    lines: list[str] = []
    for raw_key, value in mapping.items():
        key = str(raw_key)
        if isinstance(value, Mapping):
            lines.extend(_render_mapping_entry(key, value, indent, newline))
        else:
            lines.append(f"{' ' * indent}{key}: {_format_scalar(value)}{newline}")
    return lines


def _replace_scalar_line(line: str, value: Any) -> str:
    raw, eol = _split_eol(line)
    match = _YAML_KEY_RE.match(raw)
    if not match:
        return line

    prefix = raw[: match.start("tail")]
    tail = match.group("tail")
    leading_space = tail[: len(tail) - len(tail.lstrip(" "))] or " "
    old_value, comment = _split_inline_comment(tail.lstrip(" "))
    rendered_value = _format_scalar(value, old_value.strip())
    rendered = f"{prefix}{leading_space}{rendered_value}"
    if comment:
        rendered = f"{rendered} {comment.lstrip()}"
    return f"{rendered}{eol}"


def _format_scalar(value: Any, old_value: str = "") -> str:
    quote_style = _quote_style(old_value)
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    elif value is None:
        rendered = "null"
    elif isinstance(value, int | float):
        rendered = str(value)
    else:
        rendered = str(value)

    if quote_style == "'":
        return _single_quote(rendered)
    if quote_style == '"':
        return _double_quote(rendered)
    if isinstance(value, str) and _requires_quotes(rendered):
        return _single_quote(rendered)
    return rendered


def _quote_style(value: str) -> str | None:
    if value.startswith("'"):
        return "'"
    if value.startswith('"'):
        return '"'
    return None


def _requires_quotes(value: str) -> bool:
    if value == "":
        return True
    lowered = value.lower()
    if lowered in {"true", "false", "null", "~", "yes", "no", "on", "off"}:
        return True
    if value != value.strip():
        return True
    if any(character in value for character in ("\n", "\r", "\t")):
        return True
    if " #" in value or ": " in value:
        return True
    return value[0] in "-?:{}[],&*!|>@`'\"%"


def _single_quote(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _double_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _split_inline_comment(value: str) -> tuple[str, str]:
    in_single = False
    in_double = False
    for index, character in enumerate(value):
        if character == "'" and not in_double:
            in_single = not in_single
        elif character == '"' and not in_single:
            in_double = not in_double
        elif (
            character == "#"
            and not in_single
            and not in_double
            and (index == 0 or value[index - 1].isspace())
        ):
            return value[:index].rstrip(), value[index:]
    return value.rstrip(), ""


def _split_eol(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _strip_eol(line: str) -> str:
    return _split_eol(line)[0]


def _has_eol(line: str) -> bool:
    return line.endswith(("\n", "\r"))
