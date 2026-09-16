# -*- coding: utf-8 -*-
#
# Copyright @ 2025 Tencent.com
"""A2A card resolver implementation."""

import json
from enum import Enum
from urllib.parse import urljoin

from pydantic import BaseModel

from trpc.http.client import Client
from trpc.trpc_abc.context import Context
from trpc.log import logger

from a2a.types import AgentCard
from a2a.client.errors import (
    A2AClientJSONError,
    A2AClientHTTPError,
)


class ResolverSource(str, Enum):
    """
    Enum representing the source of an AgentCard.

    This enum is used to track where the AgentCard was retrieved from.
    """

    URL = "url"
    AGENT_SERVICE = "agent_service"
    # Add more sources as needed in the future


class ResolverResult(BaseModel):
    """
    A class that contains an AgentCard and its source.

    The source field indicates where the AgentCard was retrieved from,
    such as URL for get_from_agent_url or NAME for get_from_agent_service.
    """

    card: AgentCard
    source: ResolverSource


class TrpcA2ACardResolver:
    """
    A class to discover and retrieve AgentCard information from A2A agents.
    """

    def __init__(self):
        """
        Initialize the TrpcA2ACardResolver.

        Args:
            client_name: The name of the client to use for discovery
        """
        self.cli = Client("trpc-a2a-default-discovery")

    async def get_from_agent_url(self,
                                 ctx: Context,
                                 agent_url: str,
                                 agent_card_path: str = "/.well-known/agent-card.json",
                                 options=None) -> ResolverResult:
        """
        Discover an AgentCard from the given agent URL.

        Args:
            ctx: The context for the HTTP request
            agent_url: The base URL of the A2A agent
            agent_card_path: The path to the agent card JSON (default: /.well-known/agent-card.json)
            options: Options for the HTTP request (e.g., timeout)
        Returns:
            ResolverResult: The agent's capabilities and metadata with source information

        Raises:
            A2AClientHTTPError: If the agent card cannot be fetched
            A2AClientJSONError: If the agent card JSON is invalid
        """
        # Ensure agent_url ends with / and agent_card_path doesn't start with /
        if not agent_url.endswith("/"):
            agent_url = agent_url + "/"
        agent_card_path = agent_card_path.lstrip("/")
        full_url = urljoin(agent_url, agent_card_path)

        logger.debug(f"Getting agent card from {full_url}")
        try:
            # Use provided options or default to empty list
            if options is None:
                options = []

            # Make the HTTP GET request
            rsp = await self.cli.get(ctx, full_url, options=options)

            # Get the response body as JSON
            rsp_json = await rsp.json()
            logger.debug(f"Agent card response: {rsp_json}")

            # Parse and validate the agent card
            card = AgentCard(**rsp_json)

            logger.debug(f"Agent card retrieved: {card.name}")
            logger.debug(f"Agent capabilities: {card.capabilities}")

            return ResolverResult(card=card, source=ResolverSource.URL)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing agent card JSON: {e}")
            raise A2AClientJSONError(str(e)) from e
        except Exception as e:
            logger.error(f"Error getting agent card: {e}")
            raise A2AClientHTTPError(500, str(e)) from e

    async def get_from_agent_service(self,
                                     ctx: Context,
                                     agent_service_name: str,
                                     agent_card_path: str = "/.well-known/agent-card.json",
                                     options=None) -> ResolverResult:
        """
        Discover an AgentCard using the agent name from a naming service.

        This method would use a naming service to resolve the agent_name to an actual URL,
        and then retrieve the agent card from that URL.

        Args:
            ctx: The context for the HTTP request
            agent_service_name: The name of the agent as registered in the naming service
            agent_card_path: The path to the agent card JSON (default: /.well-known/agent-card.json)
            options: Options for the HTTP request (e.g., timeout)
        Returns:
            ResolverResult: The agent's capabilities and metadata with source information

        Raises:
            A2AClientHTTPError: If the agent card cannot be fetched
            A2AClientJSONError: If the agent card JSON is invalid
            NotImplementedError: This method is not yet implemented
        """
        agent_url = "trpc://trpc-agent-card-resolver.com"
        agent_card_path = agent_card_path.lstrip("/")
        full_url = "/".join([agent_url, agent_card_path])
        cli = Client(agent_service_name)

        logger.debug(f"Getting agent card from {full_url}")
        try:
            # Use provided options or default to empty list
            if options is None:
                options = []
            # Make the HTTP GET request
            rsp = await cli.get(ctx, full_url, options=options)

            # Get the response body as JSON
            rsp_json = await rsp.json()
            logger.debug(f"Agent card response: {rsp_json}")

            # Parse and validate the agent card
            card = AgentCard(**rsp_json)

            logger.debug(f"Agent card retrieved: {card.name}")
            logger.debug(f"Agent capabilities: {card.capabilities}")

            return ResolverResult(card=card, source=ResolverSource.AGENT_SERVICE)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing agent card JSON: {e}")
            raise A2AClientJSONError(str(e)) from e
        except Exception as e:
            logger.error(f"Error getting agent card: {e}")
            raise A2AClientHTTPError(500, str(e)) from e
