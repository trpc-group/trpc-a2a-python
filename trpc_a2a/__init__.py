# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""tRPC-A2A Server Implementation"""

from .server import TrpcA2AService
from .server import register_service
from .server import get_a2a_request_context
from .server import set_a2a_request_context
from .server import get_trpc_ctx

__all__ = [
    "TrpcA2AService",
    "register_service",
    "get_a2a_request_context",
    "set_a2a_request_context",
    "get_trpc_ctx",
]
