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
        logger.info(f"FlowWebSocketEventListener.setup_listeners called with bus_id: {bus_id}")
        
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
            print(f"\n=== FLOW EVENT LISTENER: FlowStartedEvent ===")
            print(f"Flow name: {event.flow_name}")
            print(f"Source: {source}")
            print(f"Event: {event}")
            print(f"=== FLOW EVENT LISTENER: FlowStartedEvent ===\n")
            logger.debug(f"Received FlowStartedEvent: {event.flow_name}")
            logger.info(f"FlowWebSocketEventListener received FlowStartedEvent!")
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Flow started: {event.flow_name} (ID: {flow_id})")
            
            # Schedule async handler
            print(f"\n=== SCHEDULING ASYNC FLOW STARTED HANDLER ===")
            print(f"Flow name: {event.flow_name}")
            print(f"=== SCHEDULING ASYNC FLOW STARTED HANDLER ===\n")
            asyncio.create_task(listener_self._handle_flow_started(flow_id, event))

        @crewai_event_bus.on(MethodExecutionStartedEvent)
        def handle_method_started(source, event: MethodExecutionStartedEvent):
            """Handle method execution started events."""
            print(f"\n=== FLOW EVENT LISTENER: MethodExecutionStartedEvent ===")
            print(f"Flow name: {event.flow_name}")
            print(f"Method name: {event.method_name}")
            print(f"Source: {source}")
            print(f"=== FLOW EVENT LISTENER: MethodExecutionStartedEvent ===\n")
            logger.debug(f"Received MethodExecutionStartedEvent: {event.flow_name}.{event.method_name}")
            logger.info(f"FlowWebSocketEventListener received MethodExecutionStartedEvent!")
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Method execution started: {event.flow_name}.{event.method_name} (ID: {flow_id})")
            
            # Schedule async handler
            print(f"\n=== SCHEDULING ASYNC METHOD STARTED HANDLER ===")
            print(f"Method: {event.method_name}")
            print(f"=== SCHEDULING ASYNC METHOD STARTED HANDLER ===\n")
            asyncio.create_task(listener_self._handle_method_started(flow_id, event))

        @crewai_event_bus.on(MethodExecutionFinishedEvent)
        def handle_method_finished(source, event: MethodExecutionFinishedEvent):
            """Handle method execution finished events."""
            print(f"\n=== FLOW EVENT LISTENER: MethodExecutionFinishedEvent ===")
            print(f"Flow name: {event.flow_name}")
            print(f"Method name: {event.method_name}")
            print(f"Source: {source}")
            print(f"=== FLOW EVENT LISTENER: MethodExecutionFinishedEvent ===\n")
            logger.debug(f"Received MethodExecutionFinishedEvent: {event.flow_name}.{event.method_name}")
            logger.info(f"FlowWebSocketEventListener received MethodExecutionFinishedEvent!")
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Method execution finished: {event.flow_name}.{event.method_name} (ID: {flow_id})")
            
            # Schedule async handler
            print(f"\n=== SCHEDULING ASYNC METHOD FINISHED HANDLER ===")
            print(f"Method: {event.method_name}")
            print(f"=== SCHEDULING ASYNC METHOD FINISHED HANDLER ===\n")
            asyncio.create_task(listener_self._handle_method_finished(flow_id, event))

        @crewai_event_bus.on(MethodExecutionFailedEvent)
        def on_method_execution_failed(source, event):
            """Handle method execution failed event."""
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Method execution failed: {event.flow_name}.{event.method_name} (ID: {flow_id})")
            
            # Schedule async handler
            print(f"\n=== SCHEDULING ASYNC METHOD FAILED HANDLER ===")
            print(f"Method: {event.method_name}")
            print(f"=== SCHEDULING ASYNC METHOD FAILED HANDLER ===\n")
            asyncio.create_task(listener_self._handle_method_failed(flow_id, event))

        @crewai_event_bus.on(FlowFinishedEvent)
        def handle_flow_finished(source, event: FlowFinishedEvent):
            """Handle flow finished events."""
            print(f"\n=== FLOW EVENT LISTENER: FlowFinishedEvent ===")
            print(f"Flow name: {event.flow_name}")
            print(f"Source: {source}")
            print(f"Event: {event}")
            print(f"=== FLOW EVENT LISTENER: FlowFinishedEvent ===\n")
            logger.debug(f"Received FlowFinishedEvent: {event.flow_name}")
            logger.info(f"FlowWebSocketEventListener received FlowFinishedEvent!")
            # Extract flow_id from the source (flow instance)
            flow_id = getattr(source, 'flow_id', str(getattr(source, 'id', id(source))))
            logger.info(f"Flow finished: {event.flow_name} (ID: {flow_id})")
            
            # Schedule async handler
            print(f"\n=== SCHEDULING ASYNC FLOW FINISHED HANDLER ===")
            print(f"Flow name: {event.flow_name}")
            print(f"=== SCHEDULING ASYNC FLOW FINISHED HANDLER ===\n")
            asyncio.create_task(listener_self._handle_flow_finished(flow_id, event))
        
        logger.info(f"Finished setting up flow event listeners for bus {bus_id}")
    
    async def _handle_flow_started(self, flow_id: str, event: FlowStartedEvent):
        """Handle flow started event asynchronously."""
        print(f"\n=== ASYNC FLOW STARTED HANDLER ===\nFlow ID: {flow_id}\nFlow Name: {event.flow_name}\n=== ASYNC FLOW STARTED HANDLER ===\n")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping, flow_id_mapping, active_flows
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        
        if api_flow_id:
            print(f"🔗 FOUND FLOW ID MAPPING: {flow_id} -> {api_flow_id}")
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
                print(f"🔗 CREATING NEW FLOW ID MAPPING: API {potential_api_flow_id} -> Internal {flow_id}")
                flow_id_mapping[potential_api_flow_id] = flow_id
                reverse_flow_id_mapping[flow_id] = potential_api_flow_id
                broadcast_flow_id = potential_api_flow_id
                print(f"📊 FLOW ID MAPPINGS UPDATED:")
                print(f"  API -> Internal: {flow_id_mapping}")
                print(f"  Internal -> API: {reverse_flow_id_mapping}")
            else:
                print(f"⚠️ NO FLOW ID MAPPING FOUND for {flow_id}, using internal ID")
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
        print(f"=== FLOW STATE STORED ===\nFlow ID: {broadcast_flow_id}\nState: {flow_state}\n=== FLOW STATE STORED ===\n")
        
        # Broadcast flow state update
        print(f"=== BROADCASTING FLOW STARTED ===\nFlow ID: {broadcast_flow_id}\n=== BROADCASTING FLOW STARTED ===\n")
        await broadcast_flow_update(broadcast_flow_id, {"type": "flow_state", "payload": flow_state})
        print(f"=== BROADCAST COMPLETE ===\nFlow ID: {broadcast_flow_id}\n=== BROADCAST COMPLETE ===\n")
    
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
        print(f"\n=== ASYNC METHOD STARTED HANDLER ===\nFlow ID: {flow_id}\nMethod: {method_name}\n=== ASYNC METHOD STARTED HANDLER ===\n")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for method execution: {broadcast_flow_id}.{method_name}")
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
            print(f"=== NEW STEP ADDED ===\nStep: {new_step}\n=== NEW STEP ADDED ===\n")
        
        flow_state["timestamp"] = asyncio.get_event_loop().time()
        
        # Broadcast flow state update
        print(f"=== BROADCASTING METHOD STARTED ===\nFlow ID: {broadcast_flow_id}\nMethod: {method_name}\n=== BROADCASTING METHOD STARTED ===\n")
        await broadcast_flow_update(broadcast_flow_id, {"type": "flow_state", "payload": flow_state})
        print(f"=== METHOD STARTED BROADCAST COMPLETE ===\nFlow ID: {broadcast_flow_id}\nMethod: {method_name}\n=== METHOD STARTED BROADCAST COMPLETE ===\n")
    
    async def _handle_method_finished(self, flow_id: str, event: MethodExecutionFinishedEvent):
        """Handle method execution finished event asynchronously."""
        method_name = event.method_name
        step_id = method_name  # Use method name as step ID
        outputs = event.result
        print(f"\n=== ASYNC METHOD FINISHED HANDLER ===\nFlow ID: {flow_id}\nMethod: {method_name}\nOutputs: {outputs}\n=== ASYNC METHOD FINISHED HANDLER ===\n")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for method completion: {broadcast_flow_id}.{method_name}")
            return
        
        flow_state = flow_states[broadcast_flow_id]
        
        # Update step status
        step_exists = False
        for step in flow_state.get("steps", []):
            if step["id"] == step_id:
                step["status"] = "completed"
                step["outputs"] = outputs
                step_exists = True
                print(f"=== STEP UPDATED TO COMPLETED ===\nStep ID: {step_id}\nOutputs: {outputs}\n=== STEP UPDATED TO COMPLETED ===\n")
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
            print(f"=== NEW COMPLETED STEP ADDED ===\nStep: {new_step}\n=== NEW COMPLETED STEP ADDED ===\n")
        
        flow_state["timestamp"] = asyncio.get_event_loop().time()
        
        # Broadcast flow state update
        print(f"=== BROADCASTING METHOD FINISHED ===\nFlow ID: {broadcast_flow_id}\nMethod: {method_name}\n=== BROADCASTING METHOD FINISHED ===\n")
        await broadcast_flow_update(broadcast_flow_id, {"type": "flow_state", "payload": flow_state})
        print(f"=== METHOD FINISHED BROADCAST COMPLETE ===\nFlow ID: {broadcast_flow_id}\nMethod: {method_name}\n=== METHOD FINISHED BROADCAST COMPLETE ===\n")
    
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
print("\n" + "="*60)
print("🎆 CREATING FLOW WEBSOCKET EVENT LISTENER 🎆")
print("="*60 + "\n")
flow_websocket_listener = FlowWebSocketEventListener()
print("\n" + "="*60)
print("✅ FLOW WEBSOCKET EVENT LISTENER CREATED ✅")
print("Setting up event listeners...")
# Import and pass the global event bus
from crewai.utilities.events.crewai_event_bus import crewai_event_bus
flow_websocket_listener.setup_listeners(crewai_event_bus)
print("✅ EVENT LISTENERS SETUP COMPLETE ✅")
print("="*60 + "\n")
