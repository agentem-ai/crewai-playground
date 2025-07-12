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


class FlowWebSocketEventListener:
    """
    Event listener for flow execution events that broadcasts updates via WebSocket.
    
    This listener captures flow events and broadcasts them to connected WebSocket
    clients for real-time UI visualization of flow execution.
    """
    
    def __init__(self):
        self.flow_states = {}
        self._registered_buses = set()
        
    def setup_listeners(self, crewai_event_bus):
        """Set up event listeners for flow visualization."""
        bus_id = id(crewai_event_bus)
        if bus_id in self._registered_buses:
            logger.info(f"Flow listeners already set up for event bus {bus_id}.")
            return

        logger.info(f"Setting up new flow listeners for event bus {bus_id}")
        self._registered_buses.add(bus_id)

        @crewai_event_bus.on(FlowStartedEvent)
        def on_flow_started(source, event):
            """Handle flow started event."""
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Flow started: {event.flow_name} (ID: {flow_id})")
            
            # Schedule async handler
            import asyncio
            if hasattr(self, 'loop'):
                asyncio.run_coroutine_threadsafe(self._handle_flow_started(flow_id, event), self.loop)
            else:
                # Try to get current loop or create new task
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(self._handle_flow_started(flow_id, event))
                except RuntimeError:
                    # No event loop running, create one
                    asyncio.create_task(self._handle_flow_started(flow_id, event))

        @crewai_event_bus.on(MethodExecutionStartedEvent)
        def on_method_execution_started(source, event):
            """Handle method execution started event."""
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Method execution started: {event.flow_name}.{event.method_name} (ID: {flow_id})")
            
            # Schedule async handler
            import asyncio
            if hasattr(self, 'loop'):
                asyncio.run_coroutine_threadsafe(self._handle_method_started(flow_id, event), self.loop)
            else:
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(self._handle_method_started(flow_id, event))
                except RuntimeError:
                    asyncio.create_task(self._handle_method_started(flow_id, event))

        @crewai_event_bus.on(MethodExecutionFinishedEvent)
        def on_method_execution_finished(source, event):
            """Handle method execution finished event."""
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Method execution finished: {event.flow_name}.{event.method_name} (ID: {flow_id})")
            
            # Schedule async handler
            import asyncio
            if hasattr(self, 'loop'):
                asyncio.run_coroutine_threadsafe(self._handle_method_finished(flow_id, event), self.loop)
            else:
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(self._handle_method_finished(flow_id, event))
                except RuntimeError:
                    asyncio.create_task(self._handle_method_finished(flow_id, event))

        @crewai_event_bus.on(MethodExecutionFailedEvent)
        def on_method_execution_failed(source, event):
            """Handle method execution failed event."""
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Method execution failed: {event.flow_name}.{event.method_name} (ID: {flow_id})")
            
            # Schedule async handler
            import asyncio
            if hasattr(self, 'loop'):
                asyncio.run_coroutine_threadsafe(self._handle_method_failed(flow_id, event), self.loop)
            else:
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(self._handle_method_failed(flow_id, event))
                except RuntimeError:
                    asyncio.create_task(self._handle_method_failed(flow_id, event))

        @crewai_event_bus.on(FlowFinishedEvent)
        def on_flow_finished(source, event):
            """Handle flow finished event."""
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Flow finished: {event.flow_name} (ID: {flow_id})")
            
            # Schedule async handler
            import asyncio
            if hasattr(self, 'loop'):
                asyncio.run_coroutine_threadsafe(self._handle_flow_finished(flow_id, event), self.loop)
            else:
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(self._handle_flow_finished(flow_id, event))
                except RuntimeError:
                    asyncio.create_task(self._handle_flow_finished(flow_id, event))
    
    async def _handle_flow_started(self, flow_id: str, event: FlowStartedEvent):
        """Handle flow started event asynchronously."""
        
        # Initialize flow state
        flow_state = {
            "id": flow_id,
            "name": event.flow_name,
            "status": "running",
            "steps": [],
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Store in global flow_states
        flow_states[flow_id] = flow_state
        
        # Broadcast flow state update
        await broadcast_flow_update(flow_id, {"type": "flow_state", "payload": flow_state})
    
    async def _handle_flow_finished(self, flow_id: str, event: FlowFinishedEvent):
        """Handle flow finished event asynchronously."""
        
        # Get current flow state
        if flow_id not in flow_states:
            logger.warning(f"No flow state found for flow completion: {flow_id}")
            return
        
        flow_state = flow_states[flow_id]
        flow_state["status"] = "completed"
        flow_state["timestamp"] = asyncio.get_event_loop().time()
        
        # Broadcast flow state update
        await broadcast_flow_update(flow_id, {"type": "flow_state", "payload": flow_state})
    
    async def _handle_method_started(self, flow_id: str, event: MethodExecutionStartedEvent):
        """Handle method execution started event asynchronously."""
        method_name = event.method_name
        step_id = method_name  # Use method name as step ID
        
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
    
    async def _handle_method_finished(self, flow_id: str, event: MethodExecutionFinishedEvent):
        """Handle method execution finished event asynchronously."""
        method_name = event.method_name
        step_id = method_name  # Use method name as step ID
        outputs = event.result
        
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
    
    async def _handle_method_failed(self, flow_id: str, event: MethodExecutionFailedEvent):
        """Handle method execution failed event asynchronously."""
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
