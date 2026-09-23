"""Реестр инструментов.

Новый инструмент = новый файл в harness/tools/ с функцией под @tool.
Файлы, начинающиеся с "_", не загружаются (образец — _template.py).
@tool(dangerous=True) — инструмент меняет что-то снаружи (отправка, запись, код):
при REQUIRE_APPROVAL=true агент спросит разрешение перед вызовом.
"""
import importlib
import inspect
import json
import pkgutil
import re
import types
import typing
from dataclasses import dataclass


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    func: typing.Callable
    dangerous: bool = False

    @property
    def openai_schema(self):
        return {"type": "function",
                "function": {"name": self.name, "description": self.description, "parameters": self.schema}}


REGISTRY: dict[str, Tool] = {}
_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


def _parse_docstring(doc):
    parts = re.split(r"^\s*Args:\s*$", doc, maxsplit=1, flags=re.M)
    params, current = {}, None
    if len(parts) > 1:
        for line in parts[1].splitlines():
            m = re.match(r"^\s*(\w+)\s*(\([^)]*\))?\s*:\s*(.*)$", line)
            if m:
                current = m.group(1)
                params[current] = m.group(3).strip()
            elif current and line.strip():
                params[current] += " " + line.strip()
    return parts[0].strip(), params


def _json_type(hint):
    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        return _json_type(args[0]) if args else "string"
    return _JSON_TYPES.get(origin or hint, "string")


def tool(func=None, *, dangerous=False):
    """Декоратор: @tool или @tool(dangerous=True)."""
    def register(f):
        description, param_docs = _parse_docstring(inspect.getdoc(f) or f.__name__)
        hints = typing.get_type_hints(f)
        props, required = {}, []
        for name, p in inspect.signature(f).parameters.items():
            prop = {"type": _json_type(hints.get(name, str))}
            if prop["type"] == "array":
                prop["items"] = {"type": "string"}
            desc = param_docs.get(name, "")
            if p.default is inspect.Parameter.empty:
                required.append(name)
            else:
                desc = f"{desc} (по умолчанию: {p.default!r})".strip()
            if desc:
                prop["description"] = desc
            props[name] = prop
        REGISTRY[f.__name__] = Tool(f.__name__, description,
                                    {"type": "object", "properties": props, "required": required},
                                    f, dangerous)
        return f

    return register(func) if func else register


_loaded = False


def load_tools():
    global _loaded
    if not _loaded:
        for mod in pkgutil.iter_modules(__path__):
            if not mod.name.startswith("_"):
                importlib.import_module(f"{__name__}.{mod.name}")
        _loaded = True
    return list(REGISTRY.values())


def run_tool(name, args):
    if name not in REGISTRY:
        raise ValueError(f"Нет инструмента '{name}'. Доступны: {', '.join(REGISTRY)}")
    if "__invalid_json__" in (args or {}):
        raise ValueError("Аргументы пришли невалидным JSON — повтори вызов с корректным JSON")
    result = REGISTRY[name].func(**(args or {}))
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)
