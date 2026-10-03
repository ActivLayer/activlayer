"""Minimal extension contract for packaging reusable tools and workers."""

from __future__ import annotations

from typing import Protocol

from .runtime import Runtime


class Extension(Protocol):
    """An extension installs one or more workers into a runtime."""

    name: str
    version: str

    def install(self, runtime: Runtime) -> None: ...


def install(runtime: Runtime, extension: Extension) -> Extension:
    extension.install(runtime)
    return extension

