"""Đường dẫn cấu trúc qua iframe/shadow mở, không chứa text/attribute nghiệp vụ."""
import json
import re

PREFIX = "runner-scope:"
STRUCTURAL_SELECTOR = re.compile(r"[a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)"
                                 r"(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)){0,39}")


def validate_path(parts):
    if not isinstance(parts, list) or not 1 <= len(parts) <= 16:
        raise ValueError("Invalid structural scope depth")
    for index, part in enumerate(parts):
        if (not isinstance(part, dict) or set(part) != {"kind", "css"} or
                part["kind"] not in ({"target"} if index == len(parts) - 1 else {"frame", "shadow"}) or
                not isinstance(part["css"], str) or len(part["css"]) > 2000 or
                not STRUCTURAL_SELECTOR.fullmatch(part["css"])):
            raise ValueError("Invalid structural scope")
        if part["kind"] == "frame" and part["css"].split(" > ")[-1].split(":")[0] not in {"iframe", "frame"}:
            raise ValueError("Invalid frame target")
    return parts


def encode(parts):
    validate_path(parts)
    if len(parts) == 1:
        return parts[0]["css"]
    value = PREFIX + json.dumps(parts, separators=(",", ":"))
    if len(value) > 2000:
        raise ValueError("Structural scope too long")
    return value


def decode(value):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError("Invalid structural locator")
    if value.startswith(PREFIX):
        return validate_path(json.loads(value[len(PREFIX):]))
    return validate_path([{"kind": "target", "css": value}])


def resolve(page, value):
    context = page
    for part in decode(value):
        if part["kind"] == "frame":
            context = context.frame_locator(part["css"])
        else:
            context = context.locator(part["css"])
    return context
