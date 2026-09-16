# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""tRPC A2A Client Example"""

from .basic_client import BasicTrpcA2AClient
from .streaming_client import StreamingTrpcA2AClient
from .multiturn_client import MultiTurnTrpcA2AClient
from .error_client import ErrorHandlingTrpcA2AClient

__all__ = [
    "BasicTrpcA2AClient",
    "StreamingTrpcA2AClient",
    "MultiTurnTrpcA2AClient",
    "ErrorHandlingTrpcA2AClient",
]
