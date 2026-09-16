# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""A2A codec implementation for tRPC-Python integration."""

from trpc.trpc_abc.codec import Codec, Message
from trpc.plugin import PluginType, register_plugin, PluginInitPos

from trpc_a2a.common import PLUGIN_NAME, VERSION


@register_plugin(
    PluginType.CLIENT_CODEC,
    PLUGIN_NAME,
    init_pos=PluginInitPos.MASTER,
    version=VERSION,
    stat_flag=True,
)
class A2AClientCodec(Codec):
    """
    A2A Client Codec for tRPC-Python.

    This codec handles encoding and decoding of A2A protocol messages.
    Since A2A operations are handled through the transport layer with
    actual request/response objects, this codec provides minimal
    encoding/decoding functionality.
    """

    @classmethod
    def encode(cls, message: Message, body: bytes) -> bytes:
        """Encode A2A message.

        Args:
            message: The tRPC message instance
            body: The message body bytes

        Returns:
            Encoded bytes (empty for A2A as encoding is handled by transport)
        """
        # A2A encoding is handled at the transport layer with A2A SDK
        # Return empty bytes as the actual data is in message headers
        return b""

    @classmethod
    def decode(cls, message: Message, body: bytes) -> bytes:
        """Decode A2A message.

        Args:
            message: The tRPC message instance
            body: The message body bytes to decode

        Returns:
            Decoded bytes
        """
        # A2A decoding is handled at the transport layer with A2A SDK
        # Return the body as-is, or convert to bytes if needed
        if body is not None:
            return body
        return bytes(str(body), encoding="utf-8")
