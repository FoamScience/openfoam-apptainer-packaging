"""Function decorators for container-as-code API.

Provides decorators for defining reusable container build functions.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


def function(func: F) -> F:
    """Decorator for Dagger-style container build functions.

    Marks a function as a reusable container build function that can be
    called from the API, shell, or YAML configuration.

    Example:
        >>> from hpctainers.api import dag, function
        >>>
        >>> @function
        >>> def my_container() -> Container:
        >>>     return (
        >>>         dag.container()
        >>>         .from_("ubuntu:24.04")
        >>>         .with_exec(["apt-get", "update"])
        >>>         .with_mpi("openmpi", "4.1.5")
        >>>     )

    Args:
        func: Function to decorate

    Returns:
        Decorated function with metadata
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.debug(f"Executing @function: {func.__name__}")
        result = func(*args, **kwargs)
        return result

    wrapper.__hpctainers_function__ = True
    wrapper.__hpctainers_name__ = func.__name__
    wrapper.__hpctainers_module__ = func.__module__

    return wrapper  # type: ignore


def object_type(name: str) -> Callable[[F], F]:
    """Decorator for defining custom container object types.

    Used to create custom types that can be composed in container builds.

    Example:
        >>> @object_type("MPIContainer")
        >>> class MPIContainer:
        >>>     def __init__(self, base: Container, implementation: str):
        >>>         self.base = base
        >>>         self.implementation = implementation

    Args:
        name: Name of the object type

    Returns:
        Decorator function
    """
    def decorator(cls: F) -> F:
        cls.__hpctainers_object_type__ = name
        return cls
    return decorator


_FUNCTION_REGISTRY: dict[str, Callable] = {}


def register_function(name: str, func: Callable) -> None:
    """Register a function in the global registry.

    Args:
        name: Function name
        func: Function to register
    """
    _FUNCTION_REGISTRY[name] = func
    logger.debug(f"Registered function: {name}")


def get_function(name: str) -> Callable | None:
    """Get a registered function by name.

    Args:
        name: Function name

    Returns:
        Function if found, None otherwise
    """
    return _FUNCTION_REGISTRY.get(name)


def list_functions() -> list[str]:
    """List all registered function names.

    Returns:
        List of function names
    """
    return list(_FUNCTION_REGISTRY.keys())
