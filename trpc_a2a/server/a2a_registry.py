# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""Service registry for A2A services."""

from typing import Dict
from typing import Optional

from .a2a_service import TrpcA2AService


class A2AServiceRegistry:
    """Registry for A2A services.

    This registry stores A2A service instances keyed by service name.
    Services must be registered before the tRPC server starts.
    """

    _services: Dict[str, TrpcA2AService] = {}

    @classmethod
    def register(cls, service_name: str, service: TrpcA2AService) -> None:
        """Register an A2A service.

        Args:
            service_name: Name of the service (must match YAML config)
            service: Instance of TrpcA2AService implementation

        Raises:
            ValueError: If service_name is already registered
        """
        if service_name in cls._services:
            raise ValueError(f"Service '{service_name}' is already registered")
        cls._services[service_name] = service

    @classmethod
    def get(cls, service_name: str) -> Optional[TrpcA2AService]:
        """Get a registered service.

        Args:
            service_name: Name of the service to retrieve

        Returns:
            TrpcA2AService instance or None if not found
        """
        return cls._services.get(service_name)

    @classmethod
    def get_all(cls) -> Dict[str, TrpcA2AService]:
        """Get all registered services.

        Returns:
            Dictionary of all registered services
        """
        return cls._services.copy()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered services.

        This is mainly useful for testing.
        """
        cls._services.clear()


def register_service(service_name: str, service: TrpcA2AService) -> None:
    """Register an A2A service.

    This is the public API for registering services.

    Args:
        service_name: Name of the service (must match YAML config)
        service: Instance of TrpcA2AService implementation

    Example:
        >>> from trpc_a2a import TrpcA2AService, register_service
        >>>
        >>> class MyAgent(TrpcA2AService):
        >>>     # ... implementation ...
        >>>
        >>> register_service("my-agent", MyAgent())
    """
    A2AServiceRegistry.register(service_name, service)
