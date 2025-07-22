"""
Event Listener for CrewAI Playground

This module provides a unified event listener that handles both Flow and Crew events.
"""

import asyncio
import logging
import json
from typing import Any, Dict, Optional
from datetime import datetime
from fastapi import WebSocket

from crewai.utilities.events import (
    # Flow Events
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
    # Task Events
    TaskStartedEvent,
    TaskCompletedEvent,
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

try:
    from crewai_playground.events import (
        CrewInitializationRequestedEvent,
        CrewInitializationCompletedEvent,
    )
except ImportError:
    # Custom events may not be available in all environments
    CrewInitializationRequestedEvent = None
    CrewInitializationCompletedEvent = None

from .websocket_utils import broadcast_flow_update
from .telemetry import telemetry_service

logger = logging.getLogger(__name__)


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return str(obj)
        try:
            return str(obj)
        except:
            return "[Unserializable Object]"
        return super().default(obj)


class EventListener:
    """Unified event listener for both flow and crew execution events."""

    def __init__(self):
        # Flow-level state management
        self.flow_states = {}

        # Crew-level state management
        self.crew_state: Dict[str, Any] = {}
        self.agent_states: Dict[str, Dict[str, Any]] = {}
        self.task_states: Dict[str, Dict[str, Any]] = {}

        # WebSocket client management
        self.clients: Dict[str, Dict[str, Any]] = {}

        # Event loop reference
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._registered_buses = set()

    def ensure_event_loop(self):
        """Ensure event loop reference is available for scheduling."""
        try:
            if not self.loop or self.loop.is_closed():
                self.loop = asyncio.get_running_loop()
                logger.info("Event loop reference updated for unified event listener")
        except RuntimeError:
            logger.warning("No running event loop available for unified event listener")

    def setup_listeners(self, crewai_event_bus):
        """Set up event listeners for both flow and crew visualization."""
        if id(crewai_event_bus) in self._registered_buses:
            logger.info("Event listeners already registered for this bus")
            return

        logger.info("Setting up unified event listeners")

        # Ensure we have an event loop reference
        self.ensure_event_loop()

        # Flow Events
        crewai_event_bus.on(FlowStartedEvent)(self.handle_flow_started)
        crewai_event_bus.on(FlowFinishedEvent)(self.handle_flow_finished)
        crewai_event_bus.on(MethodExecutionStartedEvent)(
            self.handle_method_execution_started
        )
        crewai_event_bus.on(MethodExecutionFinishedEvent)(
            self.handle_method_execution_finished
        )
        crewai_event_bus.on(MethodExecutionFailedEvent)(
            self.handle_method_execution_failed
        )

        # Crew Events
        crewai_event_bus.on(CrewKickoffStartedEvent)(self.handle_crew_kickoff_started)
        crewai_event_bus.on(CrewKickoffCompletedEvent)(
            self.handle_crew_kickoff_completed
        )
        crewai_event_bus.on(CrewKickoffFailedEvent)(self.handle_crew_kickoff_failed)
        crewai_event_bus.on(CrewTestStartedEvent)(self.handle_crew_test_started)
        crewai_event_bus.on(CrewTestCompletedEvent)(self.handle_crew_test_completed)
        crewai_event_bus.on(CrewTestFailedEvent)(self.handle_crew_test_failed)
        crewai_event_bus.on(CrewTrainStartedEvent)(self.handle_crew_train_started)
        crewai_event_bus.on(CrewTrainCompletedEvent)(self.handle_crew_train_completed)
        crewai_event_bus.on(CrewTrainFailedEvent)(self.handle_crew_train_failed)

        # Agent Events
        crewai_event_bus.on(AgentExecutionStartedEvent)(
            self.handle_agent_execution_started
        )
        crewai_event_bus.on(AgentExecutionCompletedEvent)(
            self.handle_agent_execution_completed
        )
        crewai_event_bus.on(AgentExecutionErrorEvent)(self.handle_agent_execution_error)

        # Task Events
        crewai_event_bus.on(TaskStartedEvent)(self.handle_task_started)
        crewai_event_bus.on(TaskCompletedEvent)(self.handle_task_completed)

        # Tool Usage Events
        crewai_event_bus.on(ToolUsageStartedEvent)(self.handle_tool_usage_started)
        crewai_event_bus.on(ToolUsageFinishedEvent)(self.handle_tool_usage_finished)
        crewai_event_bus.on(ToolUsageErrorEvent)(self.handle_tool_usage_error)
        crewai_event_bus.on(ToolValidateInputErrorEvent)(
            self.handle_tool_validate_input_error
        )
        crewai_event_bus.on(ToolExecutionErrorEvent)(self.handle_tool_execution_error)
        crewai_event_bus.on(ToolSelectionErrorEvent)(self.handle_tool_selection_error)

        # LLM Events
        crewai_event_bus.on(LLMCallStartedEvent)(self.handle_llm_call_started)
        crewai_event_bus.on(LLMCallCompletedEvent)(self.handle_llm_call_completed)
        crewai_event_bus.on(LLMCallFailedEvent)(self.handle_llm_call_failed)
        crewai_event_bus.on(LLMStreamChunkEvent)(self.handle_llm_stream_chunk)

        # Custom Events (if available)
        if CrewInitializationRequestedEvent:
            crewai_event_bus.on(CrewInitializationRequestedEvent)(
                self.handle_crew_initialization_requested
            )
        if CrewInitializationCompletedEvent:
            crewai_event_bus.on(CrewInitializationCompletedEvent)(
                self.handle_crew_initialization_completed
            )

        self._registered_buses.add(id(crewai_event_bus))
        logger.info("Unified event listeners registered successfully")

    # WebSocket Client Management
    async def connect(self, websocket: WebSocket, client_id: str, crew_id: str = None):
        """Connect a new WebSocket client."""
        try:
            await websocket.accept()

            self.clients[client_id] = {
                "websocket": websocket,
                "crew_id": crew_id,
                "connected_at": datetime.utcnow().isoformat(),
                "last_ping": datetime.utcnow().isoformat(),
                "connection_status": "active",
            }

            logger.info(
                f"WebSocket client {client_id} connected for crew {crew_id}. Total connections: {len(self.clients)}"
            )

            # Send current state to the newly connected client
            if crew_id:
                try:
                    await self.send_state_to_client(client_id)
                except Exception as e:
                    logger.error(f"Error sending initial state to client {client_id}: {e}")
                    # Don't disconnect on initial state send failure
                    
        except Exception as e:
            logger.error(f"Error accepting WebSocket connection for client {client_id}: {e}")
            # Clean up if connection failed
            if client_id in self.clients:
                del self.clients[client_id]
            raise

    def disconnect(self, client_id: str):
        """Disconnect a client by ID."""
        if client_id not in self.clients:
            logger.warning(f"Attempted to disconnect non-existent client {client_id}")
            return
        self._safe_disconnect(client_id)

    async def register_client_for_crew(self, client_id: str, crew_id: str):
        """Register a client for updates from a specific crew."""
        try:
            if client_id in self.clients:
                old_crew_id = self.clients[client_id].get("crew_id")
                self.clients[client_id]["crew_id"] = crew_id
                self.clients[client_id]["last_ping"] = datetime.utcnow().isoformat()
                logger.info(f"Client {client_id} registered for crew {crew_id} (was: {old_crew_id})")
                
                # Send current state for the new crew
                try:
                    await self.send_state_to_client(client_id)
                except Exception as e:
                    logger.error(f"Error sending state after crew registration for client {client_id}: {e}")
            else:
                logger.warning(f"Attempted to register non-existent client {client_id} for crew {crew_id}")
        except Exception as e:
            logger.error(f"Error registering client {client_id} for crew {crew_id}: {e}")

    async def send_state_to_client(self, client_id: str):
        """Send current state to a specific client."""
        if client_id not in self.clients:
            logger.warning(f"Client {client_id} not found in connected clients")
            return

        client = self.clients[client_id]
        websocket = client["websocket"]
        client_crew_id = client.get("crew_id")
        current_crew_id = self.crew_state.get("id") if self.crew_state else None
        
        logger.debug(f"Sending state to client {client_id}, client_crew_id: {client_crew_id}, current_crew_id: {current_crew_id}")

        # Check if we have flow state for this crew first
        flow_state = None
        for fid, state in self.flow_states.items():
            if (client_crew_id and 
                (state.get("name") == client_crew_id or state.get("id") == client_crew_id)):
                flow_state = state
                break

        # Send flow state if available
        if flow_state:
            try:
                await websocket.send_text(
                    json.dumps(
                        {"type": "flow_state", "payload": flow_state},
                        cls=CustomJSONEncoder,
                    )
                )
                logger.info(f"Sent flow state to client {client_id}")
                return
            except Exception as e:
                logger.error(f"Error sending flow state to client {client_id}: {str(e)}")
                self.disconnect(client_id)
                return
        
        # Send crew state (with more lenient matching)
        should_send_crew_state = (
            not client_crew_id or  # Client has no crew filter
            not current_crew_id or  # No current crew (send current state anyway)
            client_crew_id == current_crew_id or  # Exact match
            client_crew_id == str(current_crew_id) or  # String comparison
            bool(self.crew_state or self.agent_states or self.task_states)  # Has any state to send
        )
        
        if should_send_crew_state:
            try:
                state = {
                    "crew": self.crew_state,
                    "agents": list(self.agent_states.values()),
                    "tasks": list(self.task_states.values()),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                json_data = json.dumps(state, cls=CustomJSONEncoder)
                await websocket.send_text(json_data)
                logger.info(f"Sent crew state to client {client_id} (crew: {bool(self.crew_state)}, agents: {len(self.agent_states)}, tasks: {len(self.task_states)})")
            except Exception as e:
                logger.error(f"Error sending crew state to client {client_id}: {str(e)}")
                self.disconnect(client_id)
        else:
            logger.debug(f"No matching state to send to client {client_id} (client_crew_id: {client_crew_id}, current_crew_id: {current_crew_id})")

    async def broadcast_update(self):
        """Broadcast the current state to all connected WebSocket clients."""
        if not self.clients:
            logger.debug("📡 No WebSocket clients connected, skipping broadcast")
            return

        # Get current crew ID from crew state
        current_crew_id = self.crew_state.get("id") if self.crew_state else None
        logger.info(f"📡 BROADCASTING UPDATE - crew_id: {current_crew_id}, clients: {len(self.clients)}")
        logger.info(f"📊 Current state summary: crew={bool(self.crew_state)}, agents={len(self.agent_states)}, tasks={len(self.task_states)}")
        
        # Prepare the state data
        state = {
            "crew": self.crew_state,
            "agents": list(self.agent_states.values()),
            "tasks": list(self.task_states.values()),
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        logger.debug(f"Broadcasting state: crew={bool(self.crew_state)}, agents={len(self.agent_states)}, tasks={len(self.task_states)}")

        # Send to all connected clients (remove restrictive filtering)
        disconnected_clients = []
        clients_snapshot = list(self.clients.items())  # Create snapshot to avoid concurrent modification
        
        for client_id, client in clients_snapshot:
            # Check if client still exists (might have been removed by another thread)
            if client_id not in self.clients:
                continue
                
            client_crew_id = client.get("crew_id")
            
            # Send to clients that match the crew or have no specific crew filter
            should_send = (
                not client_crew_id or  # Client has no crew filter
                not current_crew_id or  # No current crew (send to all)
                client_crew_id == current_crew_id or  # Exact crew match
                client_crew_id == str(current_crew_id)  # String comparison fallback
            )
            
            if should_send:
                try:
                    websocket = client["websocket"]
                    json_data = json.dumps(state, cls=CustomJSONEncoder)
                    await websocket.send_text(json_data)
                    logger.debug(f"Successfully sent update to client {client_id} for crew {client_crew_id}")
                except Exception as e:
                    logger.error(f"Error broadcasting to client {client_id}: {str(e)}")
                    disconnected_clients.append(client_id)
            else:
                logger.debug(f"Skipping client {client_id} (crew filter: {client_crew_id}, current: {current_crew_id})")
        
        # Clean up disconnected clients with thread-safe removal
        for client_id in disconnected_clients:
            self._safe_disconnect(client_id)

    def _safe_disconnect(self, client_id: str):
        try:
            if client_id in self.clients:
                client = self.clients[client_id]
                crew_id = client.get("crew_id")
                del self.clients[client_id]
                logger.info(
                    f"WebSocket client {client_id} (crew: {crew_id}) disconnected. Remaining connections: {len(self.clients)}"
                )
        except Exception as e:
            logger.error(f"Error during client {client_id} disconnect: {e}")

    def reset_state(self):
        """Reset the state when a new execution starts."""
        self.crew_state = {}
        self.agent_states = {}
        self.task_states = {}

    # Utility Methods
    def _schedule(self, coro):
        """Schedule coroutine safely on an event loop."""
        try:
            # Try to get the current running loop
            loop = asyncio.get_running_loop()
            # Create task on the running loop
            loop.create_task(coro)
        except RuntimeError:
            # No running loop, try to create a new one or use thread pool
            try:
                # Try to use the stored loop if available
                if self.loop and not self.loop.is_closed():
                    # Schedule on the stored loop using call_soon_threadsafe
                    future = asyncio.run_coroutine_threadsafe(coro, self.loop)
                    # Don't wait for the result to avoid blocking
                else:
                    logger.warning(
                        "No running event loop found and no stored loop available"
                    )
            except Exception as e:
                logger.error(f"Error scheduling coroutine: {e}")

    def _extract_execution_id(self, source, event):
        """Extract execution ID from source or event."""
        # Try to get from event first (more reliable for crew events)
        if hasattr(event, "execution_id"):
            return str(event.execution_id)
        elif hasattr(event, "crew_id"):
            return str(event.crew_id)
        elif hasattr(event, "id"):
            return str(event.id)
        elif hasattr(event, "_id"):
            return str(event._id)
        elif hasattr(event, "flow_id"):
            return str(event.flow_id)
        
        # Try to get from source
        if hasattr(source, "id"):
            return str(source.id)
        elif hasattr(source, "_id"):
            return str(source._id)
        elif hasattr(source, "execution_id"):
            return str(source.execution_id)
        elif hasattr(source, "crew_id"):
            return str(source.crew_id)
        
        # For crew objects, try to get name or other identifiers
        if hasattr(source, "name"):
            return str(source.name)
        elif hasattr(source, "__class__"):
            class_name = source.__class__.__name__
            if "crew" in class_name.lower():
                return f"{class_name}_{id(source)}"
        
        # Fallback to object id
        execution_id = str(id(source)) if source else str(id(event))
        logger.debug(f"Using fallback execution_id: {execution_id} for source: {type(source)}, event: {type(event)}")
        return execution_id

    def _is_flow_context(self, source, event) -> bool:
        """Determine if this event is in a flow context."""
        # Check if source is a Flow object
        if hasattr(source, "__class__") and "Flow" in source.__class__.__name__:
            return True
        # Check if source has flow-like attributes
        if hasattr(source, "state") and hasattr(source, "id"):
            return True
        # Check event for flow indicators
        if hasattr(event, "flow_id"):
            return True
        return False

    def get_flow_state(self, flow_id: str):
        """Get the current state of a flow."""
        return self.flow_states.get(flow_id)

    def _ensure_flow_state_exists(
        self, flow_id: str, event_name: str, flow_name: str = None
    ):
        """Ensure flow state exists for the given flow ID."""
        try:
            from .flow_api import reverse_flow_id_mapping

            api_flow_id = reverse_flow_id_mapping.get(flow_id)
            broadcast_flow_id = api_flow_id if api_flow_id else flow_id
        except ImportError:
            broadcast_flow_id = flow_id

        if broadcast_flow_id not in self.flow_states:
            logger.info(
                f"Creating new flow state for {broadcast_flow_id} (event: {event_name})"
            )
            self.flow_states[broadcast_flow_id] = {
                "id": broadcast_flow_id,
                "name": flow_name or f"Flow {broadcast_flow_id}",
                "status": "running",
                "steps": [],
                "timestamp": asyncio.get_event_loop().time(),
            }

        return broadcast_flow_id, self.flow_states[broadcast_flow_id]

    # Event Handlers
    def handle_flow_started(self, source, event):
        """Handle flow started event."""
        flow_id = self._extract_execution_id(source, event)
        if flow_id:
            self._schedule(self._handle_flow_started(flow_id, event, source))

    def handle_flow_finished(self, source, event):
        """Handle flow finished event."""
        flow_id = self._extract_execution_id(source, event)
        if flow_id:
            self._schedule(self._handle_flow_finished(flow_id, event, source))

    def handle_method_execution_started(self, source, event):
        """Handle method execution started event."""
        flow_id = self._extract_execution_id(source, event)
        if flow_id:
            self._schedule(self._handle_method_started(flow_id, event))

    def handle_method_execution_finished(self, source, event):
        """Handle method execution finished event."""
        flow_id = self._extract_execution_id(source, event)
        if flow_id:
            self._schedule(self._handle_method_finished(flow_id, event))

    def handle_method_execution_failed(self, source, event):
        """Handle method execution failed event."""
        flow_id = self._extract_execution_id(source, event)
        if flow_id:
            self._schedule(self._handle_method_failed(flow_id, event))

    def handle_crew_kickoff_started(self, source, event):
        """Handle crew kickoff started event."""
        logger.info(f"🚀 CREW KICKOFF STARTED - Event received: {event}")
        logger.info(f"📊 Event source: {type(source).__name__}, Event type: {type(event).__name__}")
        logger.info(f"🔍 Source details: {source}")
        execution_id = self._extract_execution_id(source, event)
        logger.info(f"🆔 Extracted execution ID: {execution_id}")
        
        if self._is_flow_context(source, event):
            # This is a flow context - handle differently
            logger.debug(f"⏭️ Crew kickoff started (flow context) for flow: {execution_id}")
            # For flows, we don't need to do anything special here
            return
        else:
            # This is a crew context
            logger.info(f"🎯 Processing crew kickoff started for execution: {execution_id}")
            logger.info(f"📡 Scheduling async handler for crew kickoff started")
            self._schedule(self._handle_crew_kickoff_started_crew(execution_id, event))

    def handle_crew_kickoff_completed(self, source, event):
        """Handle crew kickoff completed event."""
        logger.info(f"🎉 CREW KICKOFF COMPLETED - Event received: {event}")
        logger.info(f"📊 Event source: {type(source).__name__}, Event type: {type(event).__name__}")
        logger.info(f"🔍 Source details: {source}")
        execution_id = self._extract_execution_id(source, event)
        logger.info(f"🆔 Extracted execution ID: {execution_id}")
        if self._is_flow_context(source, event):
            logger.debug(
                f"⏭️ Crew kickoff completed (flow context) for flow: {execution_id}"
            )
        else:
            logger.info(f"🎯 Processing crew kickoff completed for execution: {execution_id}")
            logger.info(f"📡 Scheduling async handler for crew kickoff completed")
            self._schedule(self._handle_crew_kickoff_completed_crew(execution_id, event))

    def handle_crew_kickoff_failed(self, source, event):
        """Handle crew kickoff failed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                logger.debug(
                    f"Crew kickoff failed (flow context) for flow: {execution_id}"
                )
            else:
                logger.info(
                    f"Crew kickoff failed (crew context) for execution: {execution_id}"
                )
                self._schedule(self._handle_crew_kickoff_failed_crew(execution_id, event))

    def handle_agent_execution_started(self, source, event):
        """Handle agent execution started event."""
        logger.info(f"Agent execution started event received: {event}")
        execution_id = self._extract_execution_id(source, event)
        
        if self._is_flow_context(source, event):
            # This is a flow context - handle differently
            logger.debug(f"Handling agent execution started in flow context: {execution_id}")
            # For flows, we don't need to do anything special here
            return
        else:
            # This is a crew context
            logger.debug(f"Handling agent execution started in crew context: {execution_id}")
            self._schedule(self._handle_agent_execution_started_crew(execution_id, event))

    def handle_agent_execution_completed(self, source, event):
        """Handle agent execution completed event."""
        logger.info(f"Agent execution completed event received: {event}")
        execution_id = self._extract_execution_id(source, event)
        
        if self._is_flow_context(source, event):
            # This is a flow context - handle differently
            logger.debug(f"Handling agent execution completed in flow context: {execution_id}")
            # For flows, we don't need to do anything special here
            return
        else:
            # This is a crew context
            logger.debug(f"Handling agent execution completed in crew context: {execution_id}")
            self._schedule(self._handle_agent_execution_completed_crew(execution_id, event))

    def handle_agent_execution_error(self, source, event):
        """Handle agent execution error event."""
        logger.info(f"Agent execution error event received: {event}")
        execution_id = self._extract_execution_id(source, event)
        
        if self._is_flow_context(source, event):
            # This is a flow context - handle differently
            logger.debug(f"Handling agent execution error in flow context: {execution_id}")
            # For flows, we don't need to do anything special here
            return
        else:
            # This is a crew context
            logger.debug(f"Handling agent execution error in crew context: {execution_id}")
            self._schedule(self._handle_agent_execution_error_crew(execution_id, event))

    # Additional Crew Event Handlers
    def handle_crew_test_started(self, source, event):
        """Handle crew test started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.info(f"Crew test started for execution: {execution_id}")
            self._schedule(self._handle_crew_test_started_crew(execution_id, event))

    def handle_crew_test_completed(self, source, event):
        """Handle crew test completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.info(f"Crew test completed for execution: {execution_id}")
            self._schedule(self._handle_crew_test_completed_crew(execution_id, event))

    def handle_crew_test_failed(self, source, event):
        """Handle crew test failed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.info(f"Crew test failed for execution: {execution_id}")
            self._schedule(self._handle_crew_test_failed_crew(execution_id, event))

    def handle_crew_train_started(self, source, event):
        """Handle crew train started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.info(f"Crew train started for execution: {execution_id}")
            self._schedule(self._handle_crew_train_started_crew(execution_id, event))

    def handle_crew_train_completed(self, source, event):
        """Handle crew train completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.info(f"Crew train completed for execution: {execution_id}")
            self._schedule(self._handle_crew_train_completed_crew(execution_id, event))

    def handle_crew_train_failed(self, source, event):
        """Handle crew train failed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.info(f"Crew train failed for execution: {execution_id}")
            self._schedule(self._handle_crew_train_failed_crew(execution_id, event))

    # Task Event Handlers
    def handle_task_started(self, source, event):
        """Handle task started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id and not self._is_flow_context(source, event):
            logger.info(f"Task started (crew context) for execution: {execution_id}")
            self._schedule(self._handle_task_started_crew(execution_id, event))

    def handle_task_completed(self, source, event):
        """Handle task completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id and not self._is_flow_context(source, event):
            logger.info(f"Task completed (crew context) for execution: {execution_id}")
            self._schedule(self._handle_task_completed_crew(execution_id, event))

    # Tool Usage Event Handlers
    def handle_tool_usage_started(self, source, event):
        """Handle tool usage started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.debug(f"Tool usage started for execution: {execution_id}")
            # Tool events are usually logged but don't need state updates

    def handle_tool_usage_finished(self, source, event):
        """Handle tool usage finished event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.debug(f"Tool usage finished for execution: {execution_id}")

    def handle_tool_usage_error(self, source, event):
        """Handle tool usage error event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.warning(f"Tool usage error for execution: {execution_id}")

    def handle_tool_validate_input_error(self, source, event):
        """Handle tool validate input error event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.warning(f"Tool validate input error for execution: {execution_id}")

    def handle_tool_execution_error(self, source, event):
        """Handle tool execution error event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.warning(f"Tool execution error for execution: {execution_id}")

    def handle_tool_selection_error(self, source, event):
        """Handle tool selection error event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.warning(f"Tool selection error for execution: {execution_id}")

    # LLM Event Handlers
    def handle_llm_call_started(self, source, event):
        """Handle LLM call started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.debug(f"LLM call started for execution: {execution_id}")

    def handle_llm_call_completed(self, source, event):
        """Handle LLM call completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.debug(f"LLM call completed for execution: {execution_id}")

    def handle_llm_call_failed(self, source, event):
        """Handle LLM call failed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.warning(f"LLM call failed for execution: {execution_id}")

    def handle_llm_stream_chunk(self, source, event):
        """Handle LLM stream chunk event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.debug(f"LLM stream chunk for execution: {execution_id}")

    # Custom Event Handlers
    def handle_crew_initialization_requested(self, source, event):
        """Handle crew initialization requested event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.info(f"Crew initialization requested for execution: {execution_id}")
            self._schedule(
                self._handle_crew_initialization_requested_crew(execution_id, event)
            )

    def handle_crew_initialization_completed(self, source, event):
        """Handle crew initialization completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            logger.info(f"Crew initialization completed for execution: {execution_id}")
            self._schedule(
                self._handle_crew_initialization_completed_crew(execution_id, event)
            )

    # Async Implementation Methods
    async def _handle_flow_started(self, flow_id: str, event, source=None):
        """Handle flow started event asynchronously."""
        logger.info(f"Flow started event handler for flow: {flow_id}")

        flow_name = getattr(event, "flow_name", f"Flow {flow_id}")
        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "flow_started", flow_name
        )

        flow_state.update(
            {
                "name": flow_name,
                "status": "running",
                "inputs": (
                    getattr(event, "inputs", {}) if hasattr(event, "inputs") else {}
                ),
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_flow_finished(self, flow_id: str, event, source=None):
        """Handle flow finished event asynchronously."""
        logger.info(f"Flow finished event handler for flow: {flow_id}")

        flow_name = getattr(event, "flow_name", f"Flow {flow_id}")
        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "flow_finished", flow_name
        )

        # Extract result from source.state if available
        result = None
        if source and hasattr(source, "state"):
            try:
                state_dict = (
                    source.state.__dict__ if hasattr(source.state, "__dict__") else {}
                )
                if "poem" in state_dict:
                    result = state_dict["poem"]
                elif "result" in state_dict:
                    result = state_dict["result"]
                elif "output" in state_dict:
                    result = state_dict["output"]
                else:
                    filtered_state = {k: v for k, v in state_dict.items() if k != "id"}
                    if filtered_state:
                        result = json.dumps(filtered_state, indent=2)
            except Exception as e:
                logger.warning(f"Error extracting result from source.state: {e}")

        if result is None and hasattr(event, "result") and event.result is not None:
            result = event.result

        flow_state.update(
            {
                "status": "completed",
                "outputs": result,
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

        logger.info(f"Flow {broadcast_flow_id} finished with result: {result}")

        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_method_started(self, flow_id: str, event):
        """Handle method execution started event asynchronously."""
        logger.info(f"Method started: {flow_id}, method: {event.method_name}")

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "method_started"
        )

        step = {
            "id": f"method_{event.method_name}_{id(event)}",
            "name": event.method_name,
            "status": "running",
            "timestamp": asyncio.get_event_loop().time(),
        }

        flow_state["steps"].append(step)

        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_method_finished(self, flow_id: str, event):
        """Handle method execution finished event asynchronously."""
        logger.info(f"Method finished: {flow_id}, method: {event.method_name}")

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "method_finished"
        )

        for step in flow_state["steps"]:
            if step["name"] == event.method_name and step["status"] == "running":
                step["status"] = "completed"
                step["timestamp"] = asyncio.get_event_loop().time()

                if hasattr(event, "outputs") and event.outputs is not None:
                    if hasattr(event.outputs, "raw"):
                        step["outputs"] = event.outputs.raw
                    else:
                        step["outputs"] = str(event.outputs)
                break

        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_method_failed(self, flow_id: str, event):
        """Handle method execution failed event asynchronously."""
        logger.info(f"Method failed: {flow_id}, method: {event.method_name}")

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "method_failed"
        )

        for step in flow_state["steps"]:
            if step["name"] == event.method_name and step["status"] == "running":
                step["status"] = "failed"
                step["timestamp"] = asyncio.get_event_loop().time()

                if hasattr(event, "error") and event.error is not None:
                    step["error"] = str(event.error)
                break

        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_kickoff_started_crew(self, execution_id: str, event):
        """Handle crew kickoff started event in crew context."""
        logger.info(f"Crew kickoff started (crew context) for execution: {execution_id}")

        # Extract crew information from event or source
        crew_name = getattr(event, "crew_name", None)
        if not crew_name and hasattr(event, "crew"):
            crew_name = getattr(event.crew, "name", None)
        if not crew_name:
            crew_name = f"Crew {execution_id}"

        self.crew_state = {
            "id": execution_id,
            "name": crew_name,
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
            "type": getattr(event, "process", "sequential"),
        }

        # Initialize agent and task states
        self.agent_states.clear()
        self.task_states.clear()
        
        # Try to extract initial agent and task information if available
        if hasattr(event, "crew") and event.crew:
            crew = event.crew
            
            # Extract agents
            if hasattr(crew, "agents") and crew.agents:
                for i, agent in enumerate(crew.agents):
                    agent_id = getattr(agent, "id", f"agent_{i}")
                    self.agent_states[agent_id] = {
                        "id": agent_id,
                        "name": getattr(agent, "name", f"Agent {i+1}"),
                        "role": getattr(agent, "role", "Unknown"),
                        "status": "initializing",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
            
            # Extract tasks
            if hasattr(crew, "tasks") and crew.tasks:
                for i, task in enumerate(crew.tasks):
                    task_id = getattr(task, "id", f"task_{i}")
                    self.task_states[task_id] = {
                        "id": task_id,
                        "description": getattr(task, "description", f"Task {i+1}"),
                        "status": "pending",
                        "agent_id": getattr(task, "agent_id", None),
                        "timestamp": datetime.utcnow().isoformat(),
                    }

        logger.info(f"Initialized crew state: {len(self.agent_states)} agents, {len(self.task_states)} tasks")
        await self.broadcast_update()

    async def _handle_crew_kickoff_completed_crew(self, execution_id: str, event):
        """Handle crew kickoff completed event in crew context."""
        logger.info(
            f"Crew kickoff completed (crew context) for execution: {execution_id}"
        )

        if self.crew_state.get("id") == execution_id:
            self.crew_state.update(
                {
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if hasattr(event, "result") and event.result is not None:
                if hasattr(event.result, "raw"):
                    self.crew_state["output"] = event.result.raw
                else:
                    self.crew_state["output"] = str(event.result)
                logger.info(f"Crew result stored as output: {self.crew_state.get('output', 'No output')[:100]}...")

            await self.broadcast_update()

    async def _handle_crew_kickoff_failed_crew(self, execution_id: str, event):
        """Handle crew kickoff failed event in crew context."""
        logger.info(f"Crew kickoff failed (crew context) for execution: {execution_id}")

        if self.crew_state.get("id") == execution_id:
            self.crew_state.update(
                {
                    "status": "failed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if hasattr(event, "error") and event.error is not None:
                self.crew_state["error"] = str(event.error)

            await self.broadcast_update()

    async def _handle_agent_execution_started_crew(self, execution_id: str, event):
        """Handle agent execution started event in crew context."""
        logger.info(
            f"Agent execution started (crew context) for execution: {execution_id}"
        )

        agent_id = getattr(event, "agent_id", f"agent_{id(event)}")
        agent_name = getattr(event, "agent_name", f"Agent {agent_id}")

        self.agent_states[agent_id] = {
            "id": agent_id,
            "name": agent_name,
            "role": getattr(event, "agent_role", "Unknown"),
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.broadcast_update()

    async def _handle_agent_execution_completed_crew(self, execution_id: str, event):
        """Handle agent execution completed event in crew context."""
        logger.info(
            f"Agent execution completed (crew context) for execution: {execution_id}"
        )

        agent_id = getattr(event, "agent_id", f"agent_{id(event)}")

        if agent_id in self.agent_states:
            self.agent_states[agent_id].update(
                {
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if hasattr(event, "result") and event.result is not None:
                self.agent_states[agent_id]["result"] = str(event.result)

            await self.broadcast_update()

    async def _handle_agent_execution_error_crew(self, execution_id: str, event):
        """Handle agent execution error event in crew context."""
        logger.info(
            f"Agent execution error (crew context) for execution: {execution_id}"
        )

        agent_id = getattr(event, "agent_id", f"agent_{id(event)}")

        if agent_id in self.agent_states:
            self.agent_states[agent_id].update(
                {
                    "status": "failed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if hasattr(event, "error") and event.error is not None:
                self.agent_states[agent_id]["error"] = str(event.error)

            await self.broadcast_update()

    # Additional async implementation methods for new event handlers
    async def _handle_crew_test_started_crew(self, execution_id: str, event):
        """Handle crew test started event in crew context."""
        logger.info(f"Crew test started (crew context) for execution: {execution_id}")

        self.crew_state = {
            "id": execution_id,
            "name": getattr(event, "crew_name", f"Crew Test {execution_id}"),
            "status": "testing",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.broadcast_update()

    async def _handle_crew_test_completed_crew(self, execution_id: str, event):
        """Handle crew test completed event in crew context."""
        logger.info(f"Crew test completed (crew context) for execution: {execution_id}")

        if self.crew_state.get("id") == execution_id:
            self.crew_state.update(
                {
                    "status": "test_completed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if hasattr(event, "result") and event.result is not None:
                self.crew_state["test_result"] = str(event.result)

            await self.broadcast_update()

    async def _handle_crew_test_failed_crew(self, execution_id: str, event):
        """Handle crew test failed event in crew context."""
        logger.info(f"Crew test failed (crew context) for execution: {execution_id}")

        if self.crew_state.get("id") == execution_id:
            self.crew_state.update(
                {
                    "status": "test_failed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if hasattr(event, "error") and event.error is not None:
                self.crew_state["test_error"] = str(event.error)

            await self.broadcast_update()

    async def _handle_crew_train_started_crew(self, execution_id: str, event):
        """Handle crew train started event in crew context."""
        logger.info(f"Crew train started (crew context) for execution: {execution_id}")

        self.crew_state = {
            "id": execution_id,
            "name": getattr(event, "crew_name", f"Crew Training {execution_id}"),
            "status": "training",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.broadcast_update()

    async def _handle_crew_train_completed_crew(self, execution_id: str, event):
        """Handle crew train completed event in crew context."""
        logger.info(
            f"Crew train completed (crew context) for execution: {execution_id}"
        )

        if self.crew_state.get("id") == execution_id:
            self.crew_state.update(
                {
                    "status": "train_completed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if hasattr(event, "result") and event.result is not None:
                self.crew_state["train_result"] = str(event.result)

            await self.broadcast_update()

    async def _handle_crew_train_failed_crew(self, execution_id: str, event):
        """Handle crew train failed event in crew context."""
        logger.info(f"Crew train failed (crew context) for execution: {execution_id}")

        if self.crew_state.get("id") == execution_id:
            self.crew_state.update(
                {
                    "status": "train_failed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if hasattr(event, "error") and event.error is not None:
                self.crew_state["train_error"] = str(event.error)

            await self.broadcast_update()

    async def _handle_task_started_crew(self, execution_id: str, event):
        """Handle task started event in crew context."""
        logger.info(f"Task started (crew context) for execution: {execution_id}")

        task_id = getattr(event, "task_id", f"task_{id(event)}")
        task_name = getattr(event, "task_name", f"Task {task_id}")

        self.task_states[task_id] = {
            "id": task_id,
            "name": task_name,
            "description": getattr(event, "task_description", ""),
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.broadcast_update()

    async def _handle_task_completed_crew(self, execution_id: str, event):
        """Handle task completed event in crew context."""
        logger.info(f"Task completed (crew context) for execution: {execution_id}")

        task_id = getattr(event, "task_id", f"task_{id(event)}")

        if task_id in self.task_states:
            self.task_states[task_id].update(
                {
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if hasattr(event, "result") and event.result is not None:
                self.task_states[task_id]["result"] = str(event.result)

            await self.broadcast_update()

    async def _handle_crew_initialization_requested_crew(
        self, execution_id: str, event
    ):
        """Handle crew initialization requested event in crew context."""
        logger.info(
            f"Crew initialization requested (crew context) for execution: {execution_id}"
        )

        self.crew_state = {
            "id": execution_id,
            "name": getattr(event, "crew_name", f"Crew {execution_id}"),
            "status": "initializing",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.broadcast_update()

    async def _handle_crew_initialization_completed_crew(
        self, execution_id: str, event
    ):
        """Handle crew initialization completed event in crew context."""
        logger.info(
            f"Crew initialization completed (crew context) for execution: {execution_id}"
        )

        if self.crew_state.get("id") == execution_id:
            self.crew_state.update(
                {
                    "status": "initialized",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            await self.broadcast_update()


# Create a singleton instance of the unified event listener
logger.info("Creating working unified event listener")
event_listener = EventListener()

# Set up the listeners with the global event bus
try:
    from crewai.utilities.events.crewai_event_bus import crewai_event_bus

    # Try to capture the current event loop if available
    try:
        event_listener.loop = asyncio.get_running_loop()
        logger.info("Captured running event loop for unified event listener")
    except RuntimeError:
        logger.info("No running event loop found during initialization")

    event_listener.setup_listeners(crewai_event_bus)
    logger.info("Working unified event listener setup completed")
except ImportError as e:
    logger.warning(f"Could not import crewai_event_bus: {e}")
except Exception as e:
    logger.error(f"Error setting up working unified event listener: {e}")
