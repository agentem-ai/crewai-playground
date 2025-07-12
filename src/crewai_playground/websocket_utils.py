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
    print(f"\n=== WEBSOCKET BROADCAST CALLED ===\nFlow ID: {flow_id}\nMessage: {message}\n=== WEBSOCKET BROADCAST CALLED ===\n")
    
    if flow_id not in flow_websocket_queues:
        print(f"=== NO WEBSOCKET CONNECTIONS ===\nFlow ID: {flow_id}\nAvailable flows: {list(flow_websocket_queues.keys())}\n=== NO WEBSOCKET CONNECTIONS ===\n")
        logger.debug(f"No WebSocket connections for flow {flow_id}")
        return

    connection_count = len(flow_websocket_queues[flow_id])
    print(f"=== BROADCASTING TO CONNECTIONS ===\nFlow ID: {flow_id}\nConnection count: {connection_count}\n=== BROADCASTING TO CONNECTIONS ===\n")
    logger.debug(f"Broadcasting message to {connection_count} WebSocket connections for flow {flow_id}")
    
    for connection_id, queue in flow_websocket_queues[flow_id].items():
        print(f"=== SENDING TO CONNECTION ===\nConnection ID: {connection_id}\n=== SENDING TO CONNECTION ===\n")
        await queue.put(message)
        print(f"=== MESSAGE QUEUED ===\nConnection ID: {connection_id}\n=== MESSAGE QUEUED ===\n")


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
