"""
Flow Event Listener for CrewAI Playground

This module provides a custom event listener for CrewAI flows to broadcast
flow execution events via WebSocket for real-time UI visualization.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from crewai.utilities.events import (
    EventListener,
    FlowStartedEvent,
    FlowFinishedEvent,
    MethodExecutionStartedEvent,
    MethodExecutionFinishedEvent,
    MethodExecutionFailedEvent,
)

from .websocket_utils import broadcast_flow_update

# Flow state cache
flow_states = {}

logger = logging.getLogger(__name__)


class FlowWebSocketEventListener(EventListener):
    """
    Event listener for flow execution events that broadcasts updates via WebSocket.
    
    This listener captures flow events and broadcasts them to connected WebSocket
    clients for real-time UI visualization of flow execution.
    """
    
    def __init__(self):
        super().__init__()
        self.flow_states = {}
        
    async def on_flow_started(self, event: FlowStartedEvent):
        """Handle flow started event."""
        flow_id = event.flow_id
        logger.info(f"Flow started: {flow_id}")
        
        # Get current flow state or initialize a new one
        if flow_id not in flow_states:
            flow_states[flow_id] = {
                "id": flow_id,
                "status": "running",
                "steps": [],
                "timestamp": asyncio.get_event_loop().time(),
                "errors": [],
            }
        
        flow_state = flow_states[flow_id]
        
        # Update flow state
        flow_state["status"] = "running"
        flow_state["timestamp"] = asyncio.get_event_loop().time()
        
        # Broadcast flow state update
        await broadcast_flow_update(flow_id, {"type": "flow_state", "payload": flow_state})
    
    async def on_flow_finished(self, event: FlowFinishedEvent):
        """Handle flow finished event."""
        flow_id = event.flow_id
        logger.info(f"Flow finished: {flow_id}")
        
        # Get current flow state
        if flow_id not in flow_states:
            logger.warning(f"No flow state found for finished flow: {flow_id}")
            return
        
        flow_state = flow_states[flow_id]
        
        # Update flow state
        flow_state["status"] = "completed"
        flow_state["outputs"] = event.outputs
        flow_state["timestamp"] = asyncio.get_event_loop().time()
        
        # Mark all steps as completed if any are still running
        for step in flow_state.get("steps", []):
            if step["status"] == "running":
                step["status"] = "completed"
        
        # Broadcast flow state update
        await broadcast_flow_update(flow_id, {"type": "flow_state", "payload": flow_state})
    
    async def on_method_execution_started(self, event: MethodExecutionStartedEvent):
        """Handle method execution started event."""
        flow_id = event.flow_id
        method_name = event.method_name
        step_id = method_name  # Use method name as step ID
        
        logger.info(f"Method execution started: {flow_id}.{method_name}")
        
        # Get current flow state
        if flow_id not in flow_states:
            logger.warning(f"No flow state found for method execution: {flow_id}.{method_name}")
            return
        
        flow_state = flow_states[flow_id]
        
        # Check if step already exists
        step_exists = False
        for step in flow_state.get("steps", []):
            if step["id"] == step_id:
                step["status"] = "running"
                step_exists = True
                break
        
        # Add step if it doesn't exist
        if not step_exists:
            new_step = {
                "id": step_id,
                "name": method_name,
                "status": "running",
                "outputs": None,
            }
            flow_state["steps"].append(new_step)
        
        flow_state["timestamp"] = asyncio.get_event_loop().time()
        
        # Broadcast flow state update
        await broadcast_flow_update(flow_id, {"type": "flow_state", "payload": flow_state})
    
    async def on_method_execution_finished(self, event: MethodExecutionFinishedEvent):
        """Handle method execution finished event."""
        flow_id = event.flow_id
        method_name = event.method_name
        step_id = method_name  # Use method name as step ID
        outputs = event.outputs
        
        logger.info(f"Method execution finished: {flow_id}.{method_name}")
        
        # Get current flow state
        if flow_id not in flow_states:
            logger.warning(f"No flow state found for method completion: {flow_id}.{method_name}")
            return
        
        flow_state = flow_states[flow_id]
        
        # Update step status
        step_exists = False
        for step in flow_state.get("steps", []):
            if step["id"] == step_id:
                step["status"] = "completed"
                step["outputs"] = outputs
                step_exists = True
                break
        
        # Add step if it doesn't exist (shouldn't happen normally)
        if not step_exists:
            new_step = {
                "id": step_id,
                "name": method_name,
                "status": "completed",
                "outputs": outputs,
            }
            flow_state["steps"].append(new_step)
        
        flow_state["timestamp"] = asyncio.get_event_loop().time()
        
        # Broadcast flow state update
        await broadcast_flow_update(flow_id, {"type": "flow_state", "payload": flow_state})
    
    async def on_method_execution_failed(self, event: MethodExecutionFailedEvent):
        """Handle method execution failed event."""
        flow_id = event.flow_id
        method_name = event.method_name
        step_id = method_name  # Use method name as step ID
        error = event.error
        
        logger.error(f"Method execution failed: {flow_id}.{method_name}: {error}")
        
        # Get current flow state
        if flow_id not in flow_states:
            logger.warning(f"No flow state found for method failure: {flow_id}.{method_name}")
            return
        
        flow_state = flow_states[flow_id]
        
        # Update step status
        step_exists = False
        for step in flow_state.get("steps", []):
            if step["id"] == step_id:
                step["status"] = "failed"
                step["error"] = str(error)
                step_exists = True
                break
        
        # Add step if it doesn't exist
        if not step_exists:
            new_step = {
                "id": step_id,
                "name": method_name,
                "status": "failed",
                "error": str(error),
            }
            flow_state["steps"].append(new_step)
        
        flow_state["timestamp"] = asyncio.get_event_loop().time()
        
        # Broadcast flow state update
        await broadcast_flow_update(flow_id, {"type": "flow_state", "payload": flow_state})
        
    def get_flow_state(self, flow_id):
        """Get the current state of a flow."""
        return flow_states.get(flow_id)


# Create a singleton instance of the event listener
flow_websocket_listener = FlowWebSocketEventListener()
