# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""tRPC-A2A client integration package."""

from .a2a_client import TrpcA2AClient
from .a2a_card_resolver import TrpcA2ACardResolver
from .utils import (
    get_a2a_client_context,
    set_a2a_client_context,
)

# Import transport and codec to ensure plugin registration
from . import a2a_transport  # noqa: F401
from . import codec  # noqa: F401

__all__ = [
    "TrpcA2AClient",
    "TrpcA2ACardResolver",
    "get_a2a_client_context",
    "set_a2a_client_context",
]
