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
    # Crew Events
    CrewKickoffStartedEvent,
    CrewKickoffCompletedEvent,
    CrewKickoffFailedEvent,
    CrewTestStartedEvent,
    CrewTestCompletedEvent,
    CrewTestFailedEvent,
    CrewTrainStartedEvent,
    CrewTrainCompletedEvent,
    CrewTrainFailedEvent,
    # Agent Events
    AgentExecutionStartedEvent,
    AgentExecutionCompletedEvent,
    AgentExecutionErrorEvent,
    # Tool Usage Events
    ToolUsageStartedEvent,
    ToolUsageFinishedEvent,
    ToolUsageErrorEvent,
    ToolValidateInputErrorEvent,
    ToolExecutionErrorEvent,
    ToolSelectionErrorEvent,
    # LLM Events
    LLMCallStartedEvent,
    LLMCallCompletedEvent,
    LLMCallFailedEvent,
    LLMStreamChunkEvent,
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
        
        listener_self = self

        # Flow Events
        @crewai_event_bus.on(FlowStartedEvent)
        def handle_flow_started(source, event: FlowStartedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Flow started event received for flow: {flow_id}")
            asyncio.create_task(listener_self._handle_flow_started(flow_id, event))

        @crewai_event_bus.on(FlowFinishedEvent)
        def handle_flow_finished(source, event: FlowFinishedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Flow finished event received for flow: {flow_id}")
            asyncio.create_task(listener_self._handle_flow_finished(flow_id, event, source))

        # Method Events
        @crewai_event_bus.on(MethodExecutionStartedEvent)
        def handle_method_execution_started(source, event: MethodExecutionStartedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(
                f"Method execution started event received for flow: {flow_id}, method: {event.method_name}"
            )
            asyncio.create_task(
                listener_self._handle_method_started(flow_id, event)
            )

        @crewai_event_bus.on(MethodExecutionFinishedEvent)
        def handle_method_execution_finished(source, event: MethodExecutionFinishedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(
                f"Method execution finished event received for flow: {flow_id}, method: {event.method_name}"
            )
            asyncio.create_task(
                listener_self._handle_method_finished(flow_id, event)
            )

        @crewai_event_bus.on(MethodExecutionFailedEvent)
        def handle_method_execution_failed(source, event: MethodExecutionFailedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(
                f"Method execution failed event received for flow: {flow_id}, method: {event.method_name}"
            )
            asyncio.create_task(listener_self._handle_method_failed(flow_id, event))

        # Crew Events
        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def handle_crew_kickoff_started(source, event: CrewKickoffStartedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Crew kickoff started event received for flow: {flow_id}, crew: {event.crew_name}")
            asyncio.create_task(listener_self._handle_crew_kickoff_started(flow_id, event))
            
        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def handle_crew_kickoff_completed(source, event: CrewKickoffCompletedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Crew kickoff completed event received for flow: {flow_id}, crew: {event.crew_name}")
            asyncio.create_task(listener_self._handle_crew_kickoff_completed(flow_id, event))
            
        @crewai_event_bus.on(CrewKickoffFailedEvent)
        def handle_crew_kickoff_failed(source, event: CrewKickoffFailedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Crew kickoff failed event received for flow: {flow_id}, crew: {event.crew_name}")
            asyncio.create_task(listener_self._handle_crew_kickoff_failed(flow_id, event))
            
        @crewai_event_bus.on(CrewTestStartedEvent)
        def handle_crew_test_started(source, event: CrewTestStartedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Crew test started event received for flow: {flow_id}, crew: {event.crew_name}")
            asyncio.create_task(listener_self._handle_crew_test_started(flow_id, event))
            
        @crewai_event_bus.on(CrewTestCompletedEvent)
        def handle_crew_test_completed(source, event: CrewTestCompletedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Crew test completed event received for flow: {flow_id}, crew: {event.crew_name}")
            asyncio.create_task(listener_self._handle_crew_test_completed(flow_id, event))
            
        @crewai_event_bus.on(CrewTestFailedEvent)
        def handle_crew_test_failed(source, event: CrewTestFailedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Crew test failed event received for flow: {flow_id}, crew: {event.crew_name}")
            asyncio.create_task(listener_self._handle_crew_test_failed(flow_id, event))
            
        @crewai_event_bus.on(CrewTrainStartedEvent)
        def handle_crew_train_started(source, event: CrewTrainStartedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Crew train started event received for flow: {flow_id}, crew: {event.crew_name}")
            asyncio.create_task(listener_self._handle_crew_train_started(flow_id, event))
            
        @crewai_event_bus.on(CrewTrainCompletedEvent)
        def handle_crew_train_completed(source, event: CrewTrainCompletedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Crew train completed event received for flow: {flow_id}, crew: {event.crew_name}")
            asyncio.create_task(listener_self._handle_crew_train_completed(flow_id, event))
            
        @crewai_event_bus.on(CrewTrainFailedEvent)
        def handle_crew_train_failed(source, event: CrewTrainFailedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Crew train failed event received for flow: {flow_id}, crew: {event.crew_name}")
            asyncio.create_task(listener_self._handle_crew_train_failed(flow_id, event))
            
        # Agent Events
        @crewai_event_bus.on(AgentExecutionStartedEvent)
        def handle_agent_execution_started(source, event: AgentExecutionStartedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            agent_role = getattr(event.agent, "role", "unknown") if hasattr(event, "agent") else "unknown"
            logger.info(f"Agent execution started event received for flow: {flow_id}, agent role: {agent_role}")
            asyncio.create_task(listener_self._handle_agent_execution_started(flow_id, event))
            
        @crewai_event_bus.on(AgentExecutionCompletedEvent)
        def handle_agent_execution_completed(source, event: AgentExecutionCompletedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            agent_role = getattr(event.agent, "role", "unknown") if hasattr(event, "agent") else "unknown"
            logger.info(f"Agent execution completed event received for flow: {flow_id}, agent role: {agent_role}")
            asyncio.create_task(listener_self._handle_agent_execution_completed(flow_id, event))
            
        @crewai_event_bus.on(AgentExecutionErrorEvent)
        def handle_agent_execution_error(source, event: AgentExecutionErrorEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            agent_role = getattr(event.agent, "role", "unknown") if hasattr(event, "agent") else "unknown"
            logger.info(f"Agent execution error event received for flow: {flow_id}, agent role: {agent_role}")
            asyncio.create_task(listener_self._handle_agent_execution_error(flow_id, event))
            
        # Tool Events
        @crewai_event_bus.on(ToolUsageStartedEvent)
        def handle_tool_usage_started(source, event: ToolUsageStartedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Tool usage started event received for flow: {flow_id}, tool: {event.tool_name}")
            asyncio.create_task(listener_self._handle_tool_usage_started(flow_id, event))
            
        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def handle_tool_usage_finished(source, event: ToolUsageFinishedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Tool usage finished event received for flow: {flow_id}, tool: {event.tool_name}")
            asyncio.create_task(listener_self._handle_tool_usage_finished(flow_id, event))
            
        @crewai_event_bus.on(ToolUsageErrorEvent)
        def handle_tool_usage_error(source, event: ToolUsageErrorEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Tool usage error event received for flow: {flow_id}, tool: {event.tool_name}")
            asyncio.create_task(listener_self._handle_tool_usage_error(flow_id, event))
            
        @crewai_event_bus.on(ToolValidateInputErrorEvent)
        def handle_tool_validate_input_error(source, event: ToolValidateInputErrorEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Tool validate input error event received for flow: {flow_id}, tool: {event.tool_name}")
            asyncio.create_task(listener_self._handle_tool_validate_input_error(flow_id, event))
            
        @crewai_event_bus.on(ToolExecutionErrorEvent)
        def handle_tool_execution_error(source, event: ToolExecutionErrorEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Tool execution error event received for flow: {flow_id}, tool: {event.tool_name}")
            asyncio.create_task(listener_self._handle_tool_execution_error(flow_id, event))
            
        @crewai_event_bus.on(ToolSelectionErrorEvent)
        def handle_tool_selection_error(source, event: ToolSelectionErrorEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"Tool selection error event received for flow: {flow_id}")
            asyncio.create_task(listener_self._handle_tool_selection_error(flow_id, event))
            
        # LLM Events
        @crewai_event_bus.on(LLMCallStartedEvent)
        def handle_llm_call_started(source, event: LLMCallStartedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            # Not logging LLM calls to avoid noise
            asyncio.create_task(listener_self._handle_llm_call_started(flow_id, event))
            
        @crewai_event_bus.on(LLMCallCompletedEvent)
        def handle_llm_call_completed(source, event: LLMCallCompletedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            # Not logging LLM calls to avoid noise
            asyncio.create_task(listener_self._handle_llm_call_completed(flow_id, event))
            
        @crewai_event_bus.on(LLMCallFailedEvent)
        def handle_llm_call_failed(source, event: LLMCallFailedEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            logger.info(f"LLM call failed event received for flow: {flow_id}")
            asyncio.create_task(listener_self._handle_llm_call_failed(flow_id, event))
            
        @crewai_event_bus.on(LLMStreamChunkEvent)
        def handle_llm_stream_chunk(source, event: LLMStreamChunkEvent):
            flow_id = getattr(source, "flow_id", str(getattr(source, "id", id(source))))
            # Not logging LLM stream chunks to avoid noise
            asyncio.create_task(listener_self._handle_llm_stream_chunk(flow_id, event))

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
        current_time = asyncio.get_event_loop().time()

        # Check if step already exists
        step_exists = False
        for step in flow_state.get("steps", []):
            if step["id"] == step_id:
                step["status"] = "running"
                step["start_time"] = current_time
                step_exists = True
                break

        # Add step if it doesn't exist
        if not step_exists:
            new_step = {
                "id": step_id,
                "name": method_name,
                "status": "running",
                "start_time": current_time,
                "outputs": None,
            }
            flow_state["steps"].append(new_step)
            logging.info(f"New step added to flow {broadcast_flow_id}: {method_name}")

        flow_state["timestamp"] = current_time

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
        current_time = asyncio.get_event_loop().time()

        # Update step status
        step_exists = False
        for step in flow_state.get("steps", []):
            if step["id"] == step_id:
                step["status"] = "completed"
                step["outputs"] = outputs
                step["end_time"] = current_time
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
                "start_time": current_time - 0.001,  # Assume a very short duration
                "end_time": current_time,
                "outputs": outputs,
            }
            flow_state["steps"].append(new_step)
            logging.info(
                f"New completed step added to flow {broadcast_flow_id}: {method_name}"
            )

        flow_state["timestamp"] = current_time

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

        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping

        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id

        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(
                f"No flow state found for method failure: {broadcast_flow_id}.{method_name}"
            )
            return

        flow_state = flow_states[broadcast_flow_id]
        current_time = asyncio.get_event_loop().time()

        # Update step status
        step_exists = False
        for step in flow_state.get("steps", []):
            if step["id"] == step_id:
                step["status"] = "failed"
                step["error"] = str(error)
                step["end_time"] = current_time
                step_exists = True
                break

        # Add step if it doesn't exist
        if not step_exists:
            new_step = {
                "id": step_id,
                "name": method_name,
                "status": "failed",
                "start_time": current_time - 0.001,  # Assume a very short duration
                "end_time": current_time,
                "error": str(error),
            }
            flow_state["steps"].append(new_step)

        flow_state["timestamp"] = current_time

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    def get_flow_state(self, flow_id):
        """Get the current state of a flow."""
        return flow_states.get(flow_id)
        
    # Crew Event Handlers
    async def _handle_crew_kickoff_started(self, flow_id: str, event):
        """Handle crew kickoff started event asynchronously."""
        logging.info(f"Crew kickoff started event handler for flow: {flow_id}, crew: {event.crew_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for crew kickoff started: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Add step for crew kickoff
        step_id = f"crew_kickoff_{event.crew_name}"
        step = {
            "id": step_id,
            "name": f"Crew Kickoff: {event.crew_name}",
            "status": "running",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Add or update step in flow state
        step_exists = False
        for i, existing_step in enumerate(flow_state["steps"]):
            if existing_step["id"] == step_id:
                flow_state["steps"][i] = step
                step_exists = True
                break
                
        if not step_exists:
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_kickoff_completed(self, flow_id: str, event):
        """Handle crew kickoff completed event asynchronously."""
        logging.info(f"Crew kickoff completed event handler for flow: {flow_id}, crew: {event.crew_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for crew kickoff completed: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Update step for crew kickoff
        step_id = f"crew_kickoff_{event.crew_name}"
        step_updated = False
        
        for i, step in enumerate(flow_state["steps"]):
            if step["id"] == step_id:
                flow_state["steps"][i]["status"] = "completed"
                flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
                
                # Extract and process the result
                output_text = None
                if hasattr(event, "result") and event.result is not None:
                    if hasattr(event.result, "raw") and event.result.raw is not None:
                        output_text = str(event.result.raw)
                    else:
                        output_text = str(event.result)
                        
                if output_text:
                    flow_state["steps"][i]["outputs"] = output_text
                    
                step_updated = True
                break
                
        if not step_updated:
            # Step not found, create a new completed step
            step = {
                "id": step_id,
                "name": f"Crew Kickoff: {event.crew_name}",
                "status": "completed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Extract and process the result
            if hasattr(event, "result") and event.result is not None:
                if hasattr(event.result, "raw") and event.result.raw is not None:
                    step["outputs"] = str(event.result.raw)
                else:
                    step["outputs"] = str(event.result)
                    
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_kickoff_failed(self, flow_id: str, event):
        """Handle crew kickoff failed event asynchronously."""
        logging.info(f"Crew kickoff failed event handler for flow: {flow_id}, crew: {event.crew_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for crew kickoff failed: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Update step for crew kickoff
        step_id = f"crew_kickoff_{event.crew_name}"
        step_updated = False
        
        for i, step in enumerate(flow_state["steps"]):
            if step["id"] == step_id:
                flow_state["steps"][i]["status"] = "failed"
                flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
                
                # Extract error message
                error_message = None
                if hasattr(event, "error") and event.error is not None:
                    error_message = str(event.error)
                    
                if error_message:
                    flow_state["steps"][i]["error"] = error_message
                    
                step_updated = True
                break
                
        if not step_updated:
            # Step not found, create a new failed step
            step = {
                "id": step_id,
                "name": f"Crew Kickoff: {event.crew_name}",
                "status": "failed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Extract error message
            if hasattr(event, "error") and event.error is not None:
                step["error"] = str(event.error)
                
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_test_started(self, flow_id: str, event):
        """Handle crew test started event asynchronously."""
        logging.info(f"Crew test started event handler for flow: {flow_id}, crew: {event.crew_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for crew test started: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Add step for crew test
        step_id = f"crew_test_{event.crew_name}"
        step = {
            "id": step_id,
            "name": f"Crew Test: {event.crew_name}",
            "status": "running",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Add or update step in flow state
        step_exists = False
        for i, existing_step in enumerate(flow_state["steps"]):
            if existing_step["id"] == step_id:
                flow_state["steps"][i] = step
                step_exists = True
                break
                
        if not step_exists:
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_test_completed(self, flow_id: str, event):
        """Handle crew test completed event asynchronously."""
        logging.info(f"Crew test completed event handler for flow: {flow_id}, crew: {event.crew_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for crew test completed: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Update step for crew test
        step_id = f"crew_test_{event.crew_name}"
        step_updated = False
        
        for i, step in enumerate(flow_state["steps"]):
            if step["id"] == step_id:
                flow_state["steps"][i]["status"] = "completed"
                flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
                
                # Extract and process the result
                output_text = None
                if hasattr(event, "result") and event.result is not None:
                    if hasattr(event.result, "raw") and event.result.raw is not None:
                        output_text = str(event.result.raw)
                    else:
                        output_text = str(event.result)
                        
                if output_text:
                    flow_state["steps"][i]["outputs"] = output_text
                    
                step_updated = True
                break
                
        if not step_updated:
            # Step not found, create a new completed step
            step = {
                "id": step_id,
                "name": f"Crew Test: {event.crew_name}",
                "status": "completed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Extract and process the result
            if hasattr(event, "result") and event.result is not None:
                if hasattr(event.result, "raw") and event.result.raw is not None:
                    step["outputs"] = str(event.result.raw)
                else:
                    step["outputs"] = str(event.result)
                    
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_test_failed(self, flow_id: str, event):
        """Handle crew test failed event asynchronously."""
        logging.info(f"Crew test failed event handler for flow: {flow_id}, crew: {event.crew_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for crew test failed: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Update step for crew test
        step_id = f"crew_test_{event.crew_name}"
        step_updated = False
        
        for i, step in enumerate(flow_state["steps"]):
            if step["id"] == step_id:
                flow_state["steps"][i]["status"] = "failed"
                flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
                
                # Extract error message
                error_message = None
                if hasattr(event, "error") and event.error is not None:
                    error_message = str(event.error)
                    
                if error_message:
                    flow_state["steps"][i]["error"] = error_message
                    
                step_updated = True
                break
                
        if not step_updated:
            # Step not found, create a new failed step
            step = {
                "id": step_id,
                "name": f"Crew Test: {event.crew_name}",
                "status": "failed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Extract error message
            if hasattr(event, "error") and event.error is not None:
                step["error"] = str(event.error)
                
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_train_started(self, flow_id: str, event):
        """Handle crew train started event asynchronously."""
        logging.info(f"Crew train started event handler for flow: {flow_id}, crew: {event.crew_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for crew train started: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Add step for crew train
        step_id = f"crew_train_{event.crew_name}"
        step = {
            "id": step_id,
            "name": f"Crew Train: {event.crew_name}",
            "status": "running",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Add or update step in flow state
        step_exists = False
        for i, existing_step in enumerate(flow_state["steps"]):
            if existing_step["id"] == step_id:
                flow_state["steps"][i] = step
                step_exists = True
                break
                
        if not step_exists:
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_train_completed(self, flow_id: str, event):
        """Handle crew train completed event asynchronously."""
        logging.info(f"Crew train completed event handler for flow: {flow_id}, crew: {event.crew_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for crew train completed: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Update step for crew train
        step_id = f"crew_train_{event.crew_name}"
        step_updated = False
        
        for i, step in enumerate(flow_state["steps"]):
            if step["id"] == step_id:
                flow_state["steps"][i]["status"] = "completed"
                flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
                
                # Extract and process the result
                output_text = None
                if hasattr(event, "result") and event.result is not None:
                    if hasattr(event.result, "raw") and event.result.raw is not None:
                        output_text = str(event.result.raw)
                    else:
                        output_text = str(event.result)
                        
                if output_text:
                    flow_state["steps"][i]["outputs"] = output_text
                    
                step_updated = True
                break
                
        if not step_updated:
            # Step not found, create a new completed step
            step = {
                "id": step_id,
                "name": f"Crew Train: {event.crew_name}",
                "status": "completed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Extract and process the result
            if hasattr(event, "result") and event.result is not None:
                if hasattr(event.result, "raw") and event.result.raw is not None:
                    step["outputs"] = str(event.result.raw)
                else:
                    step["outputs"] = str(event.result)
                    
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_train_failed(self, flow_id: str, event):
        """Handle crew train failed event asynchronously."""
        logging.info(f"Crew train failed event handler for flow: {flow_id}, crew: {event.crew_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for crew train failed: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Update step for crew train
        step_id = f"crew_train_{event.crew_name}"
        step_updated = False
        
        for i, step in enumerate(flow_state["steps"]):
            if step["id"] == step_id:
                flow_state["steps"][i]["status"] = "failed"
                flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
                
                # Extract error message
                error_message = None
                if hasattr(event, "error") and event.error is not None:
                    error_message = str(event.error)
                    
                if error_message:
                    flow_state["steps"][i]["error"] = error_message
                    
                step_updated = True
                break
                
        if not step_updated:
            # Step not found, create a new failed step
            step = {
                "id": step_id,
                "name": f"Crew Train: {event.crew_name}",
                "status": "failed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Extract error message
            if hasattr(event, "error") and event.error is not None:
                step["error"] = str(event.error)
                
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    # Agent Event Handlers
    async def _handle_agent_execution_started(self, flow_id: str, event):
        """Handle agent execution started event asynchronously."""
        logging.info(f"Agent execution started event handler for flow: {flow_id}, agent: {event.agent_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for agent execution started: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Add step for agent execution
        step_id = f"agent_execution_{event.agent_name}_{event.task_id if hasattr(event, 'task_id') else id(event)}"
        step = {
            "id": step_id,
            "name": f"Agent: {event.agent_name}",
            "status": "running",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Add task description if available
        if hasattr(event, "task_description") and event.task_description:
            step["task"] = event.task_description
        
        # Add or update step in flow state
        step_exists = False
        for i, existing_step in enumerate(flow_state["steps"]):
            if existing_step["id"] == step_id:
                flow_state["steps"][i] = step
                step_exists = True
                break
                
        if not step_exists:
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_agent_execution_completed(self, flow_id: str, event):
        """Handle agent execution completed event asynchronously."""
        logging.info(f"Agent execution completed event handler for flow: {flow_id}, agent: {event.agent_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for agent execution completed: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Update step for agent execution
        step_id = f"agent_execution_{event.agent_name}_{event.task_id if hasattr(event, 'task_id') else id(event)}"
        step_updated = False
        
        for i, step in enumerate(flow_state["steps"]):
            if step["id"] == step_id:
                flow_state["steps"][i]["status"] = "completed"
                flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
                
                # Extract and process the result
                output_text = None
                if hasattr(event, "output") and event.output is not None:
                    output_text = str(event.output)
                        
                if output_text:
                    flow_state["steps"][i]["outputs"] = output_text
                    
                step_updated = True
                break
                
        if not step_updated:
            # Step not found, create a new completed step
            step = {
                "id": step_id,
                "name": f"Agent: {event.agent_name}",
                "status": "completed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Add task description if available
            if hasattr(event, "task_description") and event.task_description:
                step["task"] = event.task_description
            
            # Extract and process the result
            if hasattr(event, "output") and event.output is not None:
                step["outputs"] = str(event.output)
                    
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_agent_execution_error(self, flow_id: str, event):
        """Handle agent execution error event asynchronously."""
        logging.info(f"Agent execution error event handler for flow: {flow_id}, agent: {event.agent_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for agent execution error: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Update step for agent execution
        step_id = f"agent_execution_{event.agent_name}_{event.task_id if hasattr(event, 'task_id') else id(event)}"
        step_updated = False
        
        for i, step in enumerate(flow_state["steps"]):
            if step["id"] == step_id:
                flow_state["steps"][i]["status"] = "failed"
                flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
                
                # Extract error message
                error_message = None
                if hasattr(event, "error") and event.error is not None:
                    error_message = str(event.error)
                    
                if error_message:
                    flow_state["steps"][i]["error"] = error_message
                    
                step_updated = True
                break
                
        if not step_updated:
            # Step not found, create a new failed step
            step = {
                "id": step_id,
                "name": f"Agent: {event.agent_name}",
                "status": "failed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Add task description if available
            if hasattr(event, "task_description") and event.task_description:
                step["task"] = event.task_description
            
            # Extract error message
            if hasattr(event, "error") and event.error is not None:
                step["error"] = str(event.error)
                
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    # Tool Event Handlers
    async def _handle_tool_usage_started(self, flow_id: str, event):
        """Handle tool usage started event asynchronously."""
        logging.info(f"Tool usage started event handler for flow: {flow_id}, tool: {event.tool_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for tool usage started: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Add step for tool usage
        step_id = f"tool_usage_{event.tool_name}_{id(event)}"
        step = {
            "id": step_id,
            "name": f"Tool: {event.tool_name}",
            "status": "running",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Add input if available
        if hasattr(event, "input") and event.input:
            step["input"] = str(event.input)
        
        # Add or update step in flow state
        step_exists = False
        for i, existing_step in enumerate(flow_state["steps"]):
            if existing_step["id"] == step_id:
                flow_state["steps"][i] = step
                step_exists = True
                break
                
        if not step_exists:
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_tool_usage_finished(self, flow_id: str, event):
        """Handle tool usage finished event asynchronously."""
        logging.info(f"Tool usage finished event handler for flow: {flow_id}, tool: {event.tool_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for tool usage finished: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Find the most recent running tool step for this tool
        tool_steps = []
        for i, step in enumerate(flow_state["steps"]):
            if step["id"].startswith(f"tool_usage_{event.tool_name}_") and step["status"] == "running":
                tool_steps.append((i, step))
        
        # Update the most recent tool step if found
        if tool_steps:
            # Sort by timestamp (most recent last)
            tool_steps.sort(key=lambda x: x[1]["timestamp"])
            i, _ = tool_steps[-1]  # Get the index of the most recent step
            
            flow_state["steps"][i]["status"] = "completed"
            flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
            
            # Extract and process the result
            output_text = None
            if hasattr(event, "output") and event.output is not None:
                output_text = str(event.output)
                    
            if output_text:
                flow_state["steps"][i]["outputs"] = output_text
        else:
            # No matching running tool step found, create a new completed step
            step_id = f"tool_usage_{event.tool_name}_{id(event)}"
            step = {
                "id": step_id,
                "name": f"Tool: {event.tool_name}",
                "status": "completed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Add input if available
            if hasattr(event, "input") and event.input:
                step["input"] = str(event.input)
            
            # Extract and process the result
            if hasattr(event, "output") and event.output is not None:
                step["outputs"] = str(event.output)
                    
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_tool_usage_error(self, flow_id: str, event):
        """Handle tool usage error event asynchronously."""
        logging.info(f"Tool usage error event handler for flow: {flow_id}, tool: {event.tool_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for tool usage error: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Find the most recent running tool step for this tool
        tool_steps = []
        for i, step in enumerate(flow_state["steps"]):
            if step["id"].startswith(f"tool_usage_{event.tool_name}_") and step["status"] == "running":
                tool_steps.append((i, step))
        
        # Update the most recent tool step if found
        if tool_steps:
            # Sort by timestamp (most recent last)
            tool_steps.sort(key=lambda x: x[1]["timestamp"])
            i, _ = tool_steps[-1]  # Get the index of the most recent step
            
            flow_state["steps"][i]["status"] = "failed"
            flow_state["steps"][i]["timestamp"] = asyncio.get_event_loop().time()
            
            # Extract error message
            error_message = None
            if hasattr(event, "error") and event.error is not None:
                error_message = str(event.error)
                
            if error_message:
                flow_state["steps"][i]["error"] = error_message
        else:
            # No matching running tool step found, create a new failed step
            step_id = f"tool_usage_{event.tool_name}_{id(event)}"
            step = {
                "id": step_id,
                "name": f"Tool: {event.tool_name}",
                "status": "failed",
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Add input if available
            if hasattr(event, "input") and event.input:
                step["input"] = str(event.input)
            
            # Extract error message
            if hasattr(event, "error") and event.error is not None:
                step["error"] = str(event.error)
                
            flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_tool_validate_input_error(self, flow_id: str, event):
        """Handle tool validate input error event asynchronously."""
        logging.info(f"Tool validate input error event handler for flow: {flow_id}, tool: {event.tool_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for tool validate input error: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Add step for tool validation error
        step_id = f"tool_validate_{event.tool_name}_{id(event)}"
        step = {
            "id": step_id,
            "name": f"Tool Validation: {event.tool_name}",
            "status": "failed",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Add input if available
        if hasattr(event, "input") and event.input:
            step["input"] = str(event.input)
        
        # Extract error message
        if hasattr(event, "error") and event.error is not None:
            step["error"] = str(event.error)
            
        flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_tool_execution_error(self, flow_id: str, event):
        """Handle tool execution error event asynchronously."""
        logging.info(f"Tool execution error event handler for flow: {flow_id}, tool: {event.tool_name}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for tool execution error: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Add step for tool execution error
        step_id = f"tool_execution_{event.tool_name}_{id(event)}"
        step = {
            "id": step_id,
            "name": f"Tool Execution: {event.tool_name}",
            "status": "failed",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Add input if available
        if hasattr(event, "input") and event.input:
            step["input"] = str(event.input)
        
        # Extract error message
        if hasattr(event, "error") and event.error is not None:
            step["error"] = str(event.error)
            
        flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_tool_selection_error(self, flow_id: str, event):
        """Handle tool selection error event asynchronously."""
        logging.info(f"Tool selection error event handler for flow: {flow_id}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for tool selection error: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Add step for tool selection error
        step_id = f"tool_selection_{id(event)}"
        step = {
            "id": step_id,
            "name": "Tool Selection",
            "status": "failed",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Extract error message
        if hasattr(event, "error") and event.error is not None:
            step["error"] = str(event.error)
            
        flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    # LLM Event Handlers
    async def _handle_llm_call_started(self, flow_id: str, event):
        """Handle LLM call started event asynchronously."""
        # Don't log LLM calls to avoid cluttering the UI
        # These events are very frequent and would add too much noise
        pass

    async def _handle_llm_call_completed(self, flow_id: str, event):
        """Handle LLM call completed event asynchronously."""
        # Don't log LLM calls to avoid cluttering the UI
        # These events are very frequent and would add too much noise
        pass

    async def _handle_llm_call_failed(self, flow_id: str, event):
        """Handle LLM call failed event asynchronously."""
        logging.info(f"LLM call failed event handler for flow: {flow_id}")
        
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
        from .flow_api import reverse_flow_id_mapping
        api_flow_id = reverse_flow_id_mapping.get(flow_id)
        broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        
        # Get current flow state
        if broadcast_flow_id not in flow_states:
            logger.warning(f"No flow state found for LLM call failed: {broadcast_flow_id}")
            return
            
        flow_state = flow_states[broadcast_flow_id]
        
        # Add step for LLM call failed
        step_id = f"llm_call_{id(event)}"
        step = {
            "id": step_id,
            "name": "LLM Call",
            "status": "failed",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Extract error message
        if hasattr(event, "error") and event.error is not None:
            step["error"] = str(event.error)
            
        flow_state["steps"].append(step)
            
        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_llm_stream_chunk(self, flow_id: str, event):
        """Handle LLM stream chunk event asynchronously."""
        # Don't process individual stream chunks to avoid excessive updates
        # These events are very frequent and would add too much noise
        pass


# Create a singleton instance of the event listener
logging.info("Creating flow WebSocket event listener")
flow_websocket_listener = FlowWebSocketEventListener()
logging.info("Flow WebSocket event listener created")
# Import and pass the global event bus
from crewai.utilities.events.crewai_event_bus import crewai_event_bus

flow_websocket_listener.setup_listeners(crewai_event_bus)
logging.info("Event listeners setup complete")
