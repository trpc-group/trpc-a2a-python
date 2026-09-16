# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""tRPC-A2A Server Implementation"""

from trpc_fastapi import get_trpc_ctx

from ._trpc_fastapi_adapter import setup_a2a_agent as _

from .a2a_service import TrpcA2AService
from .a2a_registry import register_service
from .utils import set_a2a_request_context
from .utils import get_a2a_request_context

__all__ = [
    "TrpcA2AService",
    "register_service",
    "get_a2a_request_context",
    "set_a2a_request_context",
    "get_trpc_ctx",
]
