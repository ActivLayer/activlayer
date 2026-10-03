"""Explicit extension loading for custom graph nodes and functions."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .graph_runtime import GraphRuntime


class Extension(Protocol):
    name: str
    version: str

    def install(self, runtime: GraphRuntime) -> None: ...


def install(runtime: GraphRuntime, extension: Extension) -> Extension:
    extension.install(runtime)
    return extension


def load_extensions(runtime: GraphRuntime, modules: list[str]) -> list[str]:
    """Load explicitly configured modules and install their exported extension."""
    installed: list[str] = []
    for module_name in modules:
        module = importlib.import_module(module_name)
        extension = getattr(module, "extension", None)
        if extension is not None:
            install(runtime, extension)
        elif callable(getattr(module, "install", None)):
            module.install(runtime)
        else:
            raise RuntimeError(
                f"Extension module '{module_name}' must export `extension` or `install(runtime)`"
            )
        installed.append(module_name)
    return installed
