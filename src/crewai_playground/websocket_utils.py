"""
WebSocket utilities for CrewAI Playground

This module provides utilities for WebSocket communication in CrewAI Playground.
"""

import asyncio
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WebSocket connection management
flow_websocket_queues: Dict[str, Dict[str, asyncio.Queue]] = {}


async def broadcast_flow_update(flow_id: str, message: Dict[str, Any]):
    """
    Broadcast a message to all WebSocket connections for a flow

    Args:
        flow_id: ID of the flow
        message: Message to broadcast
    """
    logger.debug(f"WebSocket broadcast called for flow {flow_id}")
    
    if flow_id not in flow_websocket_queues:
        logger.debug(f"No WebSocket connections for flow {flow_id}. Available flows: {list(flow_websocket_queues.keys())}")
        return

    connection_count = len(flow_websocket_queues[flow_id])
    logger.debug(f"Broadcasting message to {connection_count} WebSocket connections for flow {flow_id}")
    
    for connection_id, queue in flow_websocket_queues[flow_id].items():
        logger.debug(f"Queuing message for connection {connection_id}")
        await queue.put(message)


def register_websocket_queue(flow_id: str, connection_id: str, queue: asyncio.Queue):
    """
    Register a WebSocket connection queue for a flow

    Args:
        flow_id: ID of the flow
        connection_id: Unique ID for the WebSocket connection
        queue: Asyncio queue for sending messages to the WebSocket
    """
    if flow_id not in flow_websocket_queues:
        flow_websocket_queues[flow_id] = {}

    flow_websocket_queues[flow_id][connection_id] = queue
    logger.info(
        f"Registered WebSocket connection {connection_id} for flow {flow_id}. "
        f"Total connections: {len(flow_websocket_queues[flow_id])}"
    )


def unregister_websocket_queue(flow_id: str, connection_id: str):
    """
    Unregister a WebSocket connection queue for a flow

    Args:
        flow_id: ID of the flow
        connection_id: Unique ID for the WebSocket connection
    """
    if flow_id in flow_websocket_queues and connection_id in flow_websocket_queues[flow_id]:
        del flow_websocket_queues[flow_id][connection_id]
        logger.info(
            f"Unregistered WebSocket connection {connection_id} for flow {flow_id}. "
            f"Remaining connections: {len(flow_websocket_queues[flow_id])}"
        )

        # Clean up empty flow entries
        if not flow_websocket_queues[flow_id]:
            del flow_websocket_queues[flow_id]
            logger.info(f"Removed empty WebSocket queue for flow {flow_id}")
