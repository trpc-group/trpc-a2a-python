# Tencent is pleased to support the open source community by making tRPC-A2A-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-A2A-Python is licensed under Apache-2.0.
"""A2A codec implementation for tRPC-Python integration."""

from typing import Optional

from trpc_sdk.abc import BaseCodec
from trpc_sdk.abc import PluginInitPos
from trpc_sdk.abc import PluginType
from trpc_sdk.abc import TrpcContext
from trpc_sdk.plugin import register_plugin

from trpc_a2a.common import PLUGIN_NAME
from trpc_a2a.common import VERSION


@register_plugin(
    PluginType.CLIENT_CODEC,
    PLUGIN_NAME,
    init_pos=PluginInitPos.WORKER,
    version=VERSION,
    report=True,
)
class A2AClientCodec(BaseCodec):
    """
    A2A Client Codec for tRPC-Python.

    A2A requests and responses travel as objects on the message heads and are
    sent by the A2A SDK inside the transport, so this codec only passes the
    body through.
    """

    def encode_data(self, context: TrpcContext, body: Optional[bytes]) -> bytes:
        """Return the request body when it is bytes, otherwise ``b""``.

        Noop serialization hands the ``_Request`` object itself to the codec;
        the transport reads it from the message head instead.

        Args:
            context: Client context. Unused.
            body: Serialized request body.

        Returns:
            ``body`` when it is bytes, otherwise ``b""``.
        """
        if isinstance(body, (bytes, bytearray)):
            return body
        return b""

    def decode_data(self, context: TrpcContext, buffer: Optional[bytes]) -> bytes:
        """Return the response buffer unchanged, or ``b""`` when there is none.

        Args:
            context: Client context. Unused.
            buffer: Bytes returned by the transport.

        Returns:
            ``buffer``, or ``b""`` when it is ``None``.
        """
        if buffer is None:
            return b""
        return buffer
