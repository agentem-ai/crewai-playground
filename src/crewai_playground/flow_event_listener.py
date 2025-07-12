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
        logger.info(
            f"FlowWebSocketEventListener.setup_listeners called with bus_id: {bus_id}"
        )

        if bus_id in self._registered_buses:
            logger.info(f"Flow listeners already set up for event bus {bus_id}.")
            return

        logger.info(f"Setting up new flow listeners for event bus {bus_id}")
        self._registered_buses.add(bus_id)

        # Store reference to self for use in nested functions
        listener_self = self

        @crewai_event_bus.on(FlowStartedEvent)
        def handle_flow_started(source, event: FlowStartedEvent):
            """Handle flow started events."""
            logger.info(f"Received FlowStartedEvent for flow: {event.flow_name}")
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Flow started: {event.flow_name} (ID: {flow_id})")

            # Schedule async handler
            asyncio.create_task(listener_self._handle_flow_started(flow_id, event))

        @crewai_event_bus.on(MethodExecutionStartedEvent)
        def handle_method_started(source, event: MethodExecutionStartedEvent):
            """Handle method execution started events."""
            logger.info(
                f"Received MethodExecutionStartedEvent: {event.flow_name}.{event.method_name}"
            )
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(
                f"Method execution started: {event.flow_name}.{event.method_name} (ID: {flow_id})"
            )

            # Schedule async handler
            asyncio.create_task(listener_self._handle_method_started(flow_id, event))

        @crewai_event_bus.on(MethodExecutionFinishedEvent)
        def handle_method_finished(source, event: MethodExecutionFinishedEvent):
            """Handle method execution finished events."""
            logger.info(
                f"Received MethodExecutionFinishedEvent: {event.flow_name}.{event.method_name}"
            )
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(
                f"Method execution finished: {event.flow_name}.{event.method_name} (ID: {flow_id})"
            )

            # Schedule async handler
            asyncio.create_task(listener_self._handle_method_finished(flow_id, event))

        @crewai_event_bus.on(MethodExecutionFailedEvent)
        def on_method_execution_failed(source, event):
            """Handle method execution failed event."""
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(
                f"Method execution failed: {event.flow_name}.{event.method_name} (ID: {flow_id})"
            )

            # Schedule async handler
            asyncio.create_task(listener_self._handle_method_failed(flow_id, event))

        @crewai_event_bus.on(FlowFinishedEvent)
        def handle_flow_finished(source, event: FlowFinishedEvent):
            """Handle flow finished events."""
            logger.info(f"Received FlowFinishedEvent for flow: {event.flow_name}")
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Flow finished: {event.flow_name} (ID: {flow_id})")

            # Schedule async handler with both source and event
            asyncio.create_task(
                listener_self._handle_flow_finished(flow_id, event, source)
            )

        logger.info(f"Finished setting up flow event listeners for bus {bus_id}")

    async def _handle_flow_started(self, flow_id: str, event: FlowStartedEvent):
        """Handle flow started event asynchronously."""
        logging.info(
            f"Flow started event received for flow: {flow_id}, name: {event.flow_name}"
        )

        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping, flow_id_mapping, active_flows

        api_flow_id = reverse_flow_id_mapping.get(flow_id)

        if api_flow_id:
            logging.info(f"Using existing flow ID mapping: {flow_id} -> {api_flow_id}")
            # Use the API flow ID for WebSocket broadcasting
            broadcast_flow_id = api_flow_id
        else:
            # Check if this internal flow ID should be mapped to an API flow ID
            # Look for an active flow that doesn't have a mapping yet
            potential_api_flow_id = None
            for api_id in active_flows.keys():
                if api_id not in flow_id_mapping:
                    potential_api_flow_id = api_id
                    break

            if potential_api_flow_id:
                logging.info(
                    f"Creating new flow ID mapping: API {potential_api_flow_id} -> Internal {flow_id}"
                )
                flow_id_mapping[potential_api_flow_id] = flow_id
                reverse_flow_id_mapping[flow_id] = potential_api_flow_id
                broadcast_flow_id = potential_api_flow_id
            else:
                logging.warning(
                    f"No flow ID mapping found for {flow_id}, using internal ID"
                )
                broadcast_flow_id = flow_id

        # Initialize flow state
        flow_state = {
            "id": broadcast_flow_id,  # Use the API flow ID for consistency
            "name": event.flow_name,
            "status": "running",
            "steps": [],
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Store in global flow_states using the broadcast flow ID
        flow_states[broadcast_flow_id] = flow_state

        # Broadcast flow state update
        logging.info(f"Broadcasting flow started event for flow: {broadcast_flow_id}")
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_flow_finished(
        self, flow_id: str, event: FlowFinishedEvent, source=None
    ):
        """Handle flow finished event asynchronously."""
        logging.info(
            f"Flow finished event received for flow: {flow_id}, name: {event.flow_name}"
        )

        # Check the source (flow instance) for the actual result
        if source:
            # Check common result attributes
            for attr in ["result", "output", "outputs", "final_result", "last_result"]:
                if hasattr(source, attr):
                    value = getattr(source, attr)

            # Check flow-specific attributes that might contain results
            if hasattr(source, "method_outputs"):
                method_outputs = getattr(source, "method_outputs")

            if hasattr(source, "state"):
                state = getattr(source, "state")

            if hasattr(source, "_method_outputs"):
                _method_outputs = getattr(source, "_method_outputs")

            # Check if it's a flow with steps/methods that might have results
            if hasattr(source, "__dict__"):
                # Check _state specifically
                if "_state" in source.__dict__:
                    _state = source.__dict__["_state"]
        else:
            print("No source provided to check for flow result")

        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping

        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id

        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(
                f"No flow state found for flow completion: {broadcast_flow_id}"
            )
            return

        flow_state = flow_states[broadcast_flow_id]
        flow_state["status"] = "completed"
        flow_state["timestamp"] = asyncio.get_event_loop().time()

        # Extract and process the result from the flow source (state)
        output_text = None

        # Try to get result from source.state first (this is where the actual result is stored)
        if source and hasattr(source, "state"):
            state = source.state
            if hasattr(state, "__dict__"):
                state_dict = state.__dict__

                # Try common result field names first
                result_fields = ["result", "output", "outputs", "final_result"]
                for field in result_fields:
                    if field in state_dict and state_dict[field] is not None:
                        output_text = str(state_dict[field])
                        break

                # If no common result field found, use the entire state as JSON
                # excluding system fields like 'id'
                if not output_text:
                    system_fields = {"id", "_id", "__dict__", "__class__"}
                    result_dict = {
                        k: v
                        for k, v in state_dict.items()
                        if k not in system_fields and not k.startswith("_")
                    }
                    if result_dict:
                        import json

                        output_text = json.dumps(result_dict, indent=2)

        # Fallback to event.result if source state doesn't have result
        if not output_text and hasattr(event, "result") and event.result is not None:
            if isinstance(event.result, str):
                output_text = event.result
            else:
                output_text = str(event.result)

        if output_text:
            flow_state["outputs"] = output_text
            logging.info(
                f"Flow {broadcast_flow_id} completed with output: {output_text[:200]}..."
                if len(str(output_text)) > 200
                else f"Flow {broadcast_flow_id} completed with output: {output_text}"
            )
        else:
            logger.warning(
                f"No result found in FlowFinishedEvent or flow state for flow {broadcast_flow_id}"
            )
            # Set a default message indicating completion without result
            flow_state["outputs"] = (
                "Flow completed successfully (no result data available)"
            )

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_method_started(
        self, flow_id: str, event: MethodExecutionStartedEvent
    ):
        """Handle method execution started event asynchronously."""
        method_name = event.method_name
        step_id = method_name  # Use method name as step ID
        logging.info(f"Method execution started: {flow_id}.{method_name}")

        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping

        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id

        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(
                f"No flow state found for method execution: {broadcast_flow_id}.{method_name}"
            )
            return

        flow_state = flow_states[broadcast_flow_id]

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
            logging.info(f"New step added to flow {broadcast_flow_id}: {method_name}")

        flow_state["timestamp"] = asyncio.get_event_loop().time()

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_method_finished(
        self, flow_id: str, event: MethodExecutionFinishedEvent
    ):
        """Handle method execution finished event asynchronously."""
        method_name = event.method_name
        step_id = method_name  # Use method name as step ID
        outputs = event.result
        logging.info(f"Method execution finished: {flow_id}.{method_name}")

        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping

        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id

        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(
                f"No flow state found for method completion: {broadcast_flow_id}.{method_name}"
            )
            return

        flow_state = flow_states[broadcast_flow_id]

        # Update step status
        step_exists = False
        for step in flow_state.get("steps", []):
            if step["id"] == step_id:
                step["status"] = "completed"
                step["outputs"] = outputs
                step_exists = True
                logging.info(
                    f"Step updated to completed: {broadcast_flow_id}.{step_id}"
                )
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
            logging.info(
                f"New completed step added to flow {broadcast_flow_id}: {method_name}"
            )

        flow_state["timestamp"] = asyncio.get_event_loop().time()

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_method_failed(
        self, flow_id: str, event: MethodExecutionFailedEvent
    ):
        """Handle method execution failed event asynchronously."""
        method_name = event.method_name
        step_id = method_name  # Use method name as step ID
        error = event.error

        logger.error(f"Method execution failed: {flow_id}.{method_name}: {error}")

        # Get current flow state
        if flow_id not in flow_states:
            logger.warning(
                f"No flow state found for method failure: {flow_id}.{method_name}"
            )
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
        await broadcast_flow_update(
            flow_id, {"type": "flow_state", "payload": flow_state}
        )

    def get_flow_state(self, flow_id):
        """Get the current state of a flow."""
        return flow_states.get(flow_id)


# Create a singleton instance of the event listener
logging.info("Creating flow WebSocket event listener")
flow_websocket_listener = FlowWebSocketEventListener()
logging.info("Flow WebSocket event listener created")
# Import and pass the global event bus
from crewai.utilities.events.crewai_event_bus import crewai_event_bus

flow_websocket_listener.setup_listeners(crewai_event_bus)
logging.info("Event listeners setup complete")
