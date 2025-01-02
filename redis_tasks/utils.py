from datetime import datetime, timezone
import importlib

__all__ = ("serialise_function", "deserialise_function", "utc_datetime", "utc_now")

from typing import Callable


def serialise_function(func: Callable) -> str:
    """Serialize a function by storing its module and name"""
    if callable(func):
        module_name = func.__module__
        func_name = func.__name__
        qual_name = func.__qualname__
        # reject local functions or lambdas
        if func_name == qual_name and func_name.isidentifier():
            return f"{module_name}.{func_name}"
    raise AttributeError("Object must be a top level callable, not a lambda or local function")


def deserialise_function(serialized_func: str) -> Callable:
    """Deserialize and return a function from its module and name."""
    module_name, function_name = serialized_func.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def utc_datetime(milliseconds: float = None, tz: timezone = timezone.utc) -> datetime | None:
    if milliseconds is None:
        return None
    return datetime.fromtimestamp(milliseconds, tz)


def utc_now(tz: timezone = timezone.utc):
    return datetime.now(tz).timestamp()
