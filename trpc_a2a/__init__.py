# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
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
