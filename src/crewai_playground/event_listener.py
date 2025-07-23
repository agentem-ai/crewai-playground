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

# broadcast_flow_update functionality is now integrated into broadcast_update method
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
            pass

    def setup_listeners(self, crewai_event_bus):
        """Set up event listeners for both flow and crew visualization."""
        if id(crewai_event_bus) in self._registered_buses:
            logger.info("Event listeners already registered for this bus")
            return

        logger.info("Setting up unified event listeners")

        # Ensure we have an event loop reference
        self.ensure_event_loop()

        # Flow Events
        @crewai_event_bus.on(FlowStartedEvent)
        def handle_flow_started(source, event):
            """Handle flow started event."""
            flow_id = self._extract_execution_id(source, event)
            if flow_id:
                self._schedule(self._handle_flow_started(flow_id, event, source))

        @crewai_event_bus.on(FlowFinishedEvent)
        def handle_flow_finished(source, event):
            """Handle flow finished event."""
            flow_id = self._extract_execution_id(source, event)
            if flow_id:
                self._schedule(self._handle_flow_finished(flow_id, event, source))

        @crewai_event_bus.on(MethodExecutionStartedEvent)
        def handle_method_execution_started(source, event):
            """Handle method execution started event."""
            flow_id = self._extract_execution_id(source, event)
            if flow_id:
                self._schedule(self._handle_method_started(flow_id, event))

        @crewai_event_bus.on(MethodExecutionFinishedEvent)
        def handle_method_execution_finished(source, event):
            """Handle method execution finished event."""
            flow_id = self._extract_execution_id(source, event)
            if flow_id:
                self._schedule(self._handle_method_finished(flow_id, event))

        @crewai_event_bus.on(MethodExecutionFailedEvent)
        def handle_method_execution_failed(source, event):
            """Handle method execution failed event."""
            flow_id = self._extract_execution_id(source, event)
            if flow_id:
                self._schedule(self._handle_method_failed(flow_id, event))

        # Crew Events
        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def handle_crew_kickoff_started(source, event):
            """Handle crew kickoff started event."""
            logger.info(f"🚀 CREW KICKOFF STARTED - Event received: {event}")
            logger.info(
                f"📊 Event source: {type(source).__name__}, Event type: {type(event).__name__}"
            )
            logger.info(f"🔍 Source details: {source}")
            execution_id = self._extract_execution_id(source, event)
            logger.info(f"🆔 Extracted execution ID: {execution_id}")

            if self._is_flow_context(source, event):
                # This is a flow context - handle differently
                logger.debug(
                    f"⏭️ Crew kickoff started (flow context) for flow: {execution_id}"
                )
                # For flows, we don't need to do anything special here
                return
            else:
                # This is a crew context
                logger.info(
                    f"🎯 Processing crew kickoff started for execution: {execution_id}"
                )
                # Add telemetry for crew kickoff started
                try:
                    crew_id = getattr(event, "crew_id", execution_id)
                    crew_name = getattr(event, "crew_name", None)

                    # If crew_name is not in event, try to get it from event.crew
                    if not crew_name and hasattr(event, "crew"):
                        crew_name = getattr(event.crew, "name", None)

                    # Fallback to a default name if still not found
                    if not crew_name:
                        crew_name = f"Crew {crew_id}"

                    logger.info(
                        f"📊 Starting telemetry trace for crew: {crew_id}, name: {crew_name}"
                    )
                    telemetry_service.start_crew_trace(crew_id, crew_name)
                except Exception as e:
                    logger.error(f"Error starting telemetry trace: {e}")

                logger.info(f"📡 Scheduling async handler for crew kickoff started")
                self._schedule(
                    self._handle_crew_kickoff_started_crew(execution_id, event)
                )

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def handle_crew_kickoff_completed(source, event):
            """Handle crew kickoff completed event."""
            logger.info(f"🎉 CREW KICKOFF COMPLETED - Event received: {event}")
            logger.info(
                f"📊 Event source: {type(source).__name__}, Event type: {type(event).__name__}"
            )
            logger.info(f"🔍 Source details: {source}")
            execution_id = self._extract_execution_id(source, event)
            logger.info(f"🆔 Extracted execution ID: {execution_id}")
            if self._is_flow_context(source, event):
                logger.debug(
                    f"⏭️ Crew kickoff completed (flow context) for flow: {execution_id}"
                )
            else:
                logger.info(
                    f"🎯 Processing crew kickoff completed for execution: {execution_id}"
                )
                # Add telemetry for crew kickoff completed
                try:
                    crew_id = getattr(event, "crew_id", execution_id)
                    output = getattr(event, "output", None)
                    logger.info(f"📊 Ending telemetry trace for crew: {crew_id}")
                    telemetry_service.end_crew_trace(crew_id, output)
                except Exception as e:
                    logger.error(f"Error ending telemetry trace: {e}")

                logger.info(f"📡 Scheduling async handler for crew kickoff completed")
                self._schedule(
                    self._handle_crew_kickoff_completed_crew(execution_id, event)
                )

        @crewai_event_bus.on(CrewKickoffFailedEvent)
        def handle_crew_kickoff_failed(source, event):
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
                    self._schedule(
                        self._handle_crew_kickoff_failed_crew(execution_id, event)
                    )

        @crewai_event_bus.on(CrewTestStartedEvent)
        def handle_crew_test_started(source, event):
            """Handle crew test started event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.info(f"Crew test started for execution: {execution_id}")
                self._schedule(self._handle_crew_test_started_crew(execution_id, event))

        @crewai_event_bus.on(CrewTestCompletedEvent)
        def handle_crew_test_completed(source, event):
            """Handle crew test completed event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.info(f"Crew test completed for execution: {execution_id}")
                self._schedule(
                    self._handle_crew_test_completed_crew(execution_id, event)
                )

        @crewai_event_bus.on(CrewTestFailedEvent)
        def handle_crew_test_failed(source, event):
            """Handle crew test failed event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.info(f"Crew test failed for execution: {execution_id}")
                self._schedule(self._handle_crew_test_failed_crew(execution_id, event))

        @crewai_event_bus.on(CrewTrainStartedEvent)
        def handle_crew_train_started(source, event):
            """Handle crew train started event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.info(f"Crew train started for execution: {execution_id}")
                self._schedule(
                    self._handle_crew_train_started_crew(execution_id, event)
                )

        @crewai_event_bus.on(CrewTrainCompletedEvent)
        def handle_crew_train_completed(source, event):
            """Handle crew train completed event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.info(f"Crew train completed for execution: {execution_id}")
                self._schedule(
                    self._handle_crew_train_completed_crew(execution_id, event)
                )

        @crewai_event_bus.on(CrewTrainFailedEvent)
        def handle_crew_train_failed(source, event):
            """Handle crew train failed event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.info(f"Crew train failed for execution: {execution_id}")
                self._schedule(self._handle_crew_train_failed_crew(execution_id, event))

        # Agent Events
        @crewai_event_bus.on(AgentExecutionStartedEvent)
        def handle_agent_execution_started(source, event):
            """Handle agent execution started event."""
            logger.debug(f"Agent execution started event received: {event}")
            execution_id = self._extract_execution_id(source, event)

            if self._is_flow_context(source, event):
                # This is a flow context - handle differently
                logger.debug(
                    f"Handling agent execution started in flow context: {execution_id}"
                )
                # For flows, we don't need to do anything special here
                return
            else:
                # This is a crew context
                logger.debug(
                    f"Handling agent execution started in crew context: {execution_id}"
                )
                # Add telemetry for agent execution started
                try:
                    crew_id = getattr(event, "crew_id", execution_id)
                    agent_id = getattr(event, "agent_id", None)
                    agent_name = getattr(event, "agent_name", None)
                    agent_role = getattr(event, "agent_role", None)

                    # If agent_role is not in event, try to get it from event.agent
                    if not agent_role and hasattr(event, "agent"):
                        agent_role = getattr(event.agent, "role", None)

                    # If still not found, use agent_name or a default
                    if not agent_role:
                        agent_role = agent_name if agent_name else "Unknown Role"

                    logger.info(
                        f"📊 Starting telemetry for agent execution: {agent_name} ({agent_id}), role: {agent_role}"
                    )
                    telemetry_service.start_agent_execution(
                        crew_id, agent_id, agent_name, agent_role
                    )
                except Exception as e:
                    logger.error(f"Error starting agent execution telemetry: {e}")

                self._schedule(
                    self._handle_agent_execution_started_crew(execution_id, event)
                )

        @crewai_event_bus.on(AgentExecutionCompletedEvent)
        def handle_agent_execution_completed(source, event):
            """Handle agent execution completed event."""
            logger.info(f"Agent execution completed event received: {event}")
            execution_id = self._extract_execution_id(source, event)

            if self._is_flow_context(source, event):
                # This is a flow context - handle differently
                logger.debug(
                    f"Handling agent execution completed in flow context: {execution_id}"
                )
                # For flows, we don't need to do anything special here
                return
            else:
                # This is a crew context
                logger.debug(
                    f"Handling agent execution completed in crew context: {execution_id}"
                )
                # Add telemetry for agent execution completed
                try:
                    crew_id = getattr(event, "crew_id", execution_id)
                    agent_id = getattr(event, "agent_id", None)
                    output = getattr(event, "output", None)
                    logger.info(f"📊 Ending telemetry for agent execution: {agent_id}")
                    telemetry_service.end_agent_execution(crew_id, agent_id, output)
                except Exception as e:
                    logger.error(f"Error ending agent execution telemetry: {e}")

                self._schedule(
                    self._handle_agent_execution_completed_crew(execution_id, event)
                )

        @crewai_event_bus.on(AgentExecutionErrorEvent)
        def handle_agent_execution_error(source, event):
            """Handle agent execution error event."""
            logger.info(f"Agent execution error event received: {event}")
            execution_id = self._extract_execution_id(source, event)

            if self._is_flow_context(source, event):
                # This is a flow context - handle differently
                logger.debug(
                    f"Handling agent execution error in flow context: {execution_id}"
                )
                # For flows, we don't need to do anything special here
                return
            else:
                # This is a crew context
                logger.debug(
                    f"Handling agent execution error in crew context: {execution_id}"
                )
                self._schedule(
                    self._handle_agent_execution_error_crew(execution_id, event)
                )

        @crewai_event_bus.on(TaskStartedEvent)
        def handle_task_started(source, event):
            """Handle task started event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id and not self._is_flow_context(source, event):
                logger.info(
                    f"Task started (crew context) for execution: {execution_id}"
                )
                # Add telemetry for task started
                try:
                    crew_id = getattr(event, "crew_id", execution_id)
                    task_id = getattr(event, "task_id", None)
                    agent_id = getattr(event, "agent_id", None)

                    # Get task description from event
                    task_description = getattr(event, "task_description", None)

                    # If task_description is not in event, try to get it from event.task
                    if not task_description and hasattr(event, "task"):
                        task_description = getattr(event.task, "description", None)

                    # If still not found, use a default
                    if not task_description:
                        task_description = f"Task {task_id}"

                    logger.info(
                        f"📊 Starting telemetry for task execution: {task_id}, description: {task_description}"
                    )
                    telemetry_service.start_task_execution(
                        crew_id, task_id, task_description, agent_id
                    )
                except Exception as e:
                    logger.error(f"Error starting task execution telemetry: {e}")

                self._schedule(self._handle_task_started_crew(execution_id, event))

        @crewai_event_bus.on(TaskCompletedEvent)
        def handle_task_completed(source, event):
            """Handle task completed event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id and not self._is_flow_context(source, event):
                logger.info(
                    f"Task completed (crew context) for execution: {execution_id}"
                )
                # Add telemetry for task completed
                try:
                    crew_id = getattr(event, "crew_id", execution_id)
                    task_id = getattr(event, "task_id", None)
                    output = getattr(event, "output", None)
                    logger.info(f"📊 Ending telemetry for task execution: {task_id}")
                    telemetry_service.end_task_execution(crew_id, task_id, output)
                except Exception as e:
                    logger.error(f"Error ending task execution telemetry: {e}")

                self._schedule(self._handle_task_completed_crew(execution_id, event))

        # Tool Usage Events
        @crewai_event_bus.on(ToolUsageStartedEvent)
        def handle_tool_usage_started(source, event):
            """Handle tool usage started event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.debug(f"Tool usage started for execution: {execution_id}")
                # Tool events are usually logged but don't need state updates

        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def handle_tool_usage_finished(source, event):
            """Handle tool usage finished event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.debug(f"Tool usage finished for execution: {execution_id}")

        @crewai_event_bus.on(ToolUsageErrorEvent)
        def handle_tool_usage_error(source, event):
            """Handle tool usage error event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.warning(f"Tool usage error for execution: {execution_id}")

        @crewai_event_bus.on(ToolValidateInputErrorEvent)
        def handle_tool_validate_input_error(source, event):
            """Handle tool validate input error event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.warning(
                    f"Tool validate input error for execution: {execution_id}"
                )

        @crewai_event_bus.on(ToolExecutionErrorEvent)
        def handle_tool_execution_error(source, event):
            """Handle tool execution error event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.warning(f"Tool execution error for execution: {execution_id}")

        @crewai_event_bus.on(ToolSelectionErrorEvent)
        def handle_tool_selection_error(source, event):
            """Handle tool selection error event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.warning(f"Tool selection error for execution: {execution_id}")

        # LLM Events
        @crewai_event_bus.on(LLMCallStartedEvent)
        def handle_llm_call_started(source, event):
            """Handle LLM call started event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.debug(f"LLM call started for execution: {execution_id}")
                # Add telemetry for LLM call started
                try:
                    crew_id = getattr(event, "crew_id", execution_id)
                    # Extract additional data if available
                    model = getattr(event, "model", None)
                    prompt = getattr(event, "prompt", None)
                    agent_id = getattr(event, "agent_id", None)
                    task_id = getattr(event, "task_id", None)

                    # Create event data
                    event_data = {
                        "model": model,
                        "prompt": prompt,
                        "agent_id": agent_id,
                        "task_id": task_id,
                    }

                    logger.debug(f"📊 Adding telemetry event for LLM call started")
                    telemetry_service.add_event(crew_id, "llm.started", event_data)
                except Exception as e:
                    logger.error(f"Error adding LLM started telemetry event: {e}")

        @crewai_event_bus.on(LLMCallCompletedEvent)
        def handle_llm_call_completed(source, event):
            """Handle LLM call completed event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.debug(f"LLM call completed for execution: {execution_id}")
                # Add telemetry for LLM call completed
                try:
                    crew_id = getattr(event, "crew_id", execution_id)
                    # Extract additional data if available
                    model = getattr(event, "model", None)
                    completion = getattr(event, "completion", None)
                    agent_id = getattr(event, "agent_id", None)
                    task_id = getattr(event, "task_id", None)
                    tokens = getattr(event, "tokens", None)

                    # Create event data
                    event_data = {
                        "model": model,
                        "completion": completion,
                        "agent_id": agent_id,
                        "task_id": task_id,
                        "tokens": tokens,
                    }

                    logger.debug(f"📊 Adding telemetry event for LLM call completed")
                    telemetry_service.add_event(crew_id, "llm.completed", event_data)
                except Exception as e:
                    logger.error(f"Error adding LLM completed telemetry event: {e}")

        @crewai_event_bus.on(LLMCallFailedEvent)
        def handle_llm_call_failed(source, event):
            """Handle LLM call failed event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.warning(f"LLM call failed for execution: {execution_id}")

        @crewai_event_bus.on(LLMStreamChunkEvent)
        def handle_llm_stream_chunk(source, event):
            """Handle LLM stream chunk event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.debug(f"LLM stream chunk for execution: {execution_id}")

        @crewai_event_bus.on(CrewInitializationRequestedEvent)
        def handle_crew_initialization_requested(source, event):
            """Handle crew initialization requested event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.info(
                    f"Crew initialization requested for execution: {execution_id}"
                )
                self._schedule(
                    self._handle_crew_initialization_requested_crew(execution_id, event)
                )

        @crewai_event_bus.on(CrewInitializationCompletedEvent)
        def handle_crew_initialization_completed(source, event):
            """Handle crew initialization completed event."""
            execution_id = self._extract_execution_id(source, event)
            if execution_id:
                logger.info(
                    f"Crew initialization completed for execution: {execution_id}"
                )
                self._schedule(
                    self._handle_crew_initialization_completed_crew(execution_id, event)
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
                    logger.error(
                        f"Error sending initial state to client {client_id}: {e}"
                    )
                    # Don't disconnect on initial state send failure

        except Exception as e:
            logger.error(
                f"Error accepting WebSocket connection for client {client_id}: {e}"
            )
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
                logger.info(
                    f"Client {client_id} registered for crew {crew_id} (was: {old_crew_id})"
                )

                # Send current state for the new crew
                try:
                    await self.send_state_to_client(client_id)
                except Exception as e:
                    logger.error(
                        f"Error sending state after crew registration for client {client_id}: {e}"
                    )
            else:
                logger.warning(
                    f"Attempted to register non-existent client {client_id} for crew {crew_id}"
                )
        except Exception as e:
            logger.error(
                f"Error registering client {client_id} for crew {crew_id}: {e}"
            )

    async def send_state_to_client(self, client_id: str):
        """Send current state to a specific client."""
        if client_id not in self.clients:
            logger.warning(f"Client {client_id} not found in connected clients")
            return

        client = self.clients[client_id]
        websocket = client["websocket"]
        client_crew_id = client.get("crew_id")
        current_crew_id = self.crew_state.get("id") if self.crew_state else None

        logger.debug(
            f"Sending state to client {client_id}, client_crew_id: {client_crew_id}, current_crew_id: {current_crew_id}"
        )

        # Check if we have flow state for this crew first
        flow_state = None
        for fid, state in self.flow_states.items():
            if client_crew_id and (
                state.get("name") == client_crew_id or state.get("id") == client_crew_id
            ):
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
                logger.error(
                    f"Error sending flow state to client {client_id}: {str(e)}"
                )
                self.disconnect(client_id)
                return

        # Send crew state (with more lenient matching)
        should_send_crew_state = (
            not client_crew_id  # Client has no crew filter
            or not current_crew_id  # No current crew (send current state anyway)
            or client_crew_id == current_crew_id  # Exact match
            or client_crew_id == str(current_crew_id)  # String comparison
            or bool(
                self.crew_state or self.agent_states or self.task_states
            )  # Has any state to send
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
                logger.info(
                    f"Sent crew state to client {client_id} (crew: {bool(self.crew_state)}, agents: {len(self.agent_states)}, tasks: {len(self.task_states)})"
                )
            except Exception as e:
                logger.error(
                    f"Error sending crew state to client {client_id}: {str(e)}"
                )
                self.disconnect(client_id)
        else:
            logger.debug(
                f"No matching state to send to client {client_id} (client_crew_id: {client_crew_id}, current_crew_id: {current_crew_id})"
            )

    async def broadcast_update(
        self, flow_id=None, flow_state=None, update_type="crew_state"
    ):
        """Broadcast updates to all connected WebSocket clients.

        Args:
            flow_id: Optional flow ID for flow updates
            flow_state: Optional flow state data for flow updates
            update_type: Type of update - "crew_state" or "flow_state"
        """
        from .entities import entity_service
        
        # Handle flow updates
        if update_type == "flow_state" and flow_id and flow_state:
            await self._broadcast_flow_update(flow_id, flow_state)
            return

        # Handle crew updates (existing logic)
        if not self.clients:
            return

        # Get current crew ID from crew state
        current_crew_id = self.crew_state.get("id") if self.crew_state else None
        current_crew_name = self.crew_state.get("name") if self.crew_state else None

        # Use entity service to get all broadcast IDs
        if current_crew_id:
            mapped_ids = entity_service.resolve_broadcast_ids(current_crew_id)
            broadcast_crew_id = entity_service.get_primary_id(current_crew_id) or current_crew_id
        else:
            mapped_ids = []
            broadcast_crew_id = None

        logger.debug(
            f"📡 BROADCASTING UPDATE - crew_id: {current_crew_id}, name: {current_crew_name}, broadcast_id: {broadcast_crew_id}"
        )
        logger.debug(f"📡 Potential matching IDs: {mapped_ids}")
        logger.debug(
            f"📊 Current state summary: crew={bool(self.crew_state)}, agents={len(self.agent_states)}, tasks={len(self.task_states)}"
        )

        # Prepare the state data
        state = {
            "crew": self.crew_state,
            "agents": list(self.agent_states.values()),
            "tasks": list(self.task_states.values()),
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Add debug info to help troubleshoot
        if self.crew_state:
            logger.debug(
                f"Crew state ID: {self.crew_state.get('id')}, Name: {self.crew_state.get('name')}"
            )

        # Send to all connected clients
        disconnected_clients = []
        clients_snapshot = list(
            self.clients.items()
        )  # Create snapshot to avoid concurrent modification

        # Count how many clients we'll send to
        matching_clients = 0

        for client_id, client in clients_snapshot:
            # Check if client still exists (might have been removed by another thread)
            if client_id not in self.clients:
                continue

            client_crew_id = client.get("crew_id")
            logger.debug(f"Checking client {client_id} with crew_id: {client_crew_id}")

            # Use entity service for broadcast decision
            should_send = entity_service.should_broadcast_to_client(current_crew_id, client_crew_id)
            
            if should_send:
                matching_clients += 1
                try:
                    websocket = client["websocket"]
                    json_data = json.dumps(state, cls=CustomJSONEncoder)
                    await websocket.send_text(json_data)
                    logger.debug(
                        f"✅ Successfully sent update to client {client_id} for crew {client_crew_id}"
                    )
                except Exception as e:
                    logger.debug(
                        f"❌ Error broadcasting to client {client_id}: {str(e)}"
                    )
                    disconnected_clients.append(client_id)
            else:
                logger.debug(
                    f"⏭️ Skipping client {client_id} (crew filter: {client_crew_id}, current: {current_crew_id})"
                )

        logger.debug(
            f"📊 Broadcast summary: sent to {matching_clients}/{len(clients_snapshot)} clients"
        )

        # Clean up disconnected clients with thread-safe removal
        for client_id in disconnected_clients:
            self._safe_disconnect(client_id)

    async def _broadcast_flow_update(self, flow_id: str, flow_state: dict):
        """Handle flow-specific broadcasting logic."""
        from .websocket_utils import flow_websocket_queues

        # Debug: Check if flow_id is actually an object ID instead of the API flow ID
        if isinstance(flow_id, int) or (isinstance(flow_id, str) and flow_id.isdigit()):
            # Try to find the correct API flow ID from the entity service
            try:
                from .entities import entity_service

                api_flow_id = entity_service.get_primary_id(str(flow_id))
                if api_flow_id:
                    flow_id = api_flow_id  # Use the API flow ID for broadcasting
                else:
                    pass
            except ImportError as e:
                pass

        flow_clients_updated = 0

        # Broadcast to flow WebSocket queues (existing flow system)
        if flow_id in flow_websocket_queues:
            connection_count = len(flow_websocket_queues[flow_id])

            message = {"type": "flow_state", "payload": flow_state}
            for connection_id, queue in flow_websocket_queues[flow_id].items():
                try:
                    await queue.put(message)
                    flow_clients_updated += 1
                except Exception as e:
                    pass
        else:
            pass

        # Also broadcast to crew clients if they might be interested in flow updates
        crew_clients_updated = 0
        if self.clients:
            logger.info(
                f"📡 Broadcasting flow update to {len(self.clients)} crew WebSocket clients"
            )

            # Prepare flow update message for crew clients
            flow_message = {
                "type": "flow_state",
                "flow_id": flow_id,
                "flow_state": flow_state,
                "timestamp": datetime.utcnow().isoformat(),
            }

            disconnected_clients = []
            clients_snapshot = list(self.clients.items())

            for client_id, client in clients_snapshot:
                if client_id not in self.clients:
                    continue

                try:
                    websocket = client["websocket"]
                    json_data = json.dumps(flow_message, cls=CustomJSONEncoder)
                    await websocket.send_text(json_data)
                    logger.info(
                        f"✅ Successfully sent flow update to crew client {client_id}"
                    )
                    crew_clients_updated += 1
                except Exception as e:
                    logger.error(
                        f"❌ Error broadcasting flow update to crew client {client_id}: {str(e)}"
                    )
                    disconnected_clients.append(client_id)

            # Clean up disconnected clients
            for client_id in disconnected_clients:
                self._safe_disconnect(client_id)
        else:
            logger.info(f"📡 No crew WebSocket clients connected for flow updates")

        # Summary logging
        total_clients_updated = flow_clients_updated + crew_clients_updated
        logger.info(
            f"📊 Flow broadcast summary: {total_clients_updated} total clients updated (flow: {flow_clients_updated}, crew: {crew_clients_updated})"
        )

        if total_clients_updated == 0:
            logger.warning(
                f"⚠️ No WebSocket clients received flow update for flow {flow_id}"
            )

    def _safe_disconnect(self, client_id: str):
        try:
            if client_id in self.clients:
                client = self.clients[client_id]
                crew_id = client.get("crew_id")
                del self.clients[client_id]
                logger.debug(
                    f"WebSocket client {client_id} (crew: {crew_id}) disconnected. Remaining connections: {len(self.clients)}"
                )
        except Exception as e:
            logger.debug(f"Error during client {client_id} disconnect: {e}")

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
        logger.debug(
            f"Using fallback execution_id: {execution_id} for source: {type(source)}, event: {type(event)}"
        )
        return execution_id

    def _extract_agent_id(self, event, source=None):
        """Extract consistent agent ID from event or source."""
        # Try event first
        if hasattr(event, "agent_id") and event.agent_id:
            return str(event.agent_id)
        elif hasattr(event, "agent") and hasattr(event.agent, "id") and event.agent.id:
            return str(event.agent.id)
        elif hasattr(event, "agent") and hasattr(event.agent, "_id") and event.agent._id:
            return str(event.agent._id)
        
        # Try source if provided
        if source:
            if hasattr(source, "id") and source.id:
                return str(source.id)
            elif hasattr(source, "_id") and source._id:
                return str(source._id)
        
        # Try to create consistent ID from agent name/role
        if hasattr(event, "agent") and hasattr(event.agent, "role") and event.agent.role:
            # Create hash-based ID for consistency
            role_hash = abs(hash(event.agent.role)) % 100000
            return f"agent_{role_hash}"
        elif hasattr(event, "agent_role") and event.agent_role:
            role_hash = abs(hash(event.agent_role)) % 100000
            return f"agent_{role_hash}"
        
        # Fallback to event-based ID
        return f"agent_{abs(id(event)) % 100000}"

    def _extract_task_id(self, event, source=None):
        """Extract consistent task ID from event or source."""
        # Try event first
        if hasattr(event, "task_id") and event.task_id:
            return str(event.task_id)
        elif hasattr(event, "task") and hasattr(event.task, "id") and event.task.id:
            return str(event.task.id)
        elif hasattr(event, "task") and hasattr(event.task, "_id") and event.task._id:
            return str(event.task._id)
        
        # Try source if provided
        if source:
            if hasattr(source, "id") and source.id:
                return str(source.id)
            elif hasattr(source, "_id") and source._id:
                return str(source._id)
        
        # Try to create consistent ID from task description
        if hasattr(event, "task") and hasattr(event.task, "description") and event.task.description:
            desc_hash = abs(hash(event.task.description[:50])) % 100000  # Use first 50 chars
            return f"task_{desc_hash}"
        elif hasattr(event, "task_description") and event.task_description:
            desc_hash = abs(hash(event.task_description[:50])) % 100000
            return f"task_{desc_hash}"
        
        # Fallback to event-based ID
        return f"task_{abs(id(event)) % 100000}"

    def _extract_agent_data(self, event, source=None):
        """Extract comprehensive agent data from event or source."""
        agent_data = {}
        
        # Try to get data from event.agent object first
        if hasattr(event, "agent") and event.agent:
            agent_obj = event.agent
            agent_data.update({
                "name": getattr(agent_obj, "name", None),
                "role": getattr(agent_obj, "role", None),
                "description": getattr(agent_obj, "description", None),
                "backstory": getattr(agent_obj, "backstory", None),
                "goal": getattr(agent_obj, "goal", None),
            })
        
        # Try to get data from event attributes
        if hasattr(event, "agent_name") and event.agent_name:
            agent_data["name"] = event.agent_name
        if hasattr(event, "agent_role") and event.agent_role:
            agent_data["role"] = event.agent_role
        if hasattr(event, "agent_description") and event.agent_description:
            agent_data["description"] = event.agent_description
        
        # Try source if provided
        if source and not agent_data.get("name"):
            if hasattr(source, "name"):
                agent_data["name"] = source.name
            if hasattr(source, "role"):
                agent_data["role"] = source.role
            if hasattr(source, "description"):
                agent_data["description"] = source.description
        
        return agent_data

    def _extract_task_data(self, event, source=None):
        """Extract comprehensive task data from event or source."""
        task_data = {}
        
        # Try to get data from event.task object first
        if hasattr(event, "task") and event.task:
            task_obj = event.task
            task_data.update({
                "name": getattr(task_obj, "name", None),
                "description": getattr(task_obj, "description", None),
                "expected_output": getattr(task_obj, "expected_output", None),
                "agent_id": getattr(task_obj, "agent_id", None),
            })
            
            # Try to get agent ID from task.agent if available
            if hasattr(task_obj, "agent") and task_obj.agent:
                if hasattr(task_obj.agent, "id"):
                    task_data["agent_id"] = str(task_obj.agent.id)
                elif hasattr(task_obj.agent, "role"):
                    # Create consistent agent ID from role
                    role_hash = abs(hash(task_obj.agent.role)) % 100000
                    task_data["agent_id"] = f"agent_{role_hash}"
        
        # Try to get data from event attributes
        if hasattr(event, "task_name") and event.task_name:
            task_data["name"] = event.task_name
        if hasattr(event, "task_description") and event.task_description:
            task_data["description"] = event.task_description
        if hasattr(event, "agent_id") and event.agent_id:
            task_data["agent_id"] = str(event.agent_id)
        
        # Try source if provided
        if source and not task_data.get("description"):
            if hasattr(source, "description"):
                task_data["description"] = source.description
            if hasattr(source, "name"):
                task_data["name"] = source.name
        
        return task_data

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
        # Convert flow_id to string if it's not already
        flow_id_str = str(flow_id)

        try:
            from .entities import entity_service

            api_flow_id = entity_service.get_primary_id(flow_id_str)
            if not api_flow_id:
                api_flow_id = entity_service.get_primary_id(flow_id)

            broadcast_flow_id = api_flow_id if api_flow_id else flow_id_str

            if (isinstance(flow_id, int) or flow_id_str.isdigit()) and not api_flow_id:
                pass

        except ImportError as e:
            broadcast_flow_id = flow_id_str

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
        else:
            logger.info(f"🔍 Using existing flow state for {broadcast_flow_id}")

        return broadcast_flow_id, self.flow_states[broadcast_flow_id]

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

        await self.broadcast_update(
            flow_id=broadcast_flow_id, flow_state=flow_state, update_type="flow_state"
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

        await self.broadcast_update(
            flow_id=broadcast_flow_id, flow_state=flow_state, update_type="flow_state"
        )

    async def _handle_method_started(self, flow_id: str, event):
        """Handle method execution started event asynchronously."""
        logger.info(f"Method started: {flow_id}, method: {event.method_name}")

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "method_started"
        )

        current_time = asyncio.get_event_loop().time()
        step_id = (
            event.method_name
        )  # Use method name to keep step consistent across events

        # Check if step already exists (e.g. re-emitted event)
        for step in flow_state["steps"]:
            if step["id"] == step_id:
                # Update status and start_time if needed
                step["status"] = "running"
                step.setdefault("start_time", current_time)
                break
        else:
            # Create new step entry
            step = {
                "id": step_id,
                "name": event.method_name,
                "status": "running",
                "start_time": current_time,
                "outputs": None,
            }
            flow_state["steps"].append(step)

        # Refresh flow timestamp
        flow_state["timestamp"] = current_time

        await self.broadcast_update(
            flow_id=broadcast_flow_id, flow_state=flow_state, update_type="flow_state"
        )

    async def _handle_method_finished(self, flow_id: str, event):
        """Handle method execution finished event asynchronously."""
        logger.info(f"Method finished: {flow_id}, method: {event.method_name}")

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "method_finished"
        )

        current_time = asyncio.get_event_loop().time()
        step_id = event.method_name
        outputs = getattr(event, "result", None)

        # Locate existing step
        for step in flow_state["steps"]:
            if step["id"] == step_id and step.get("status") in {"running", "failed"}:
                step.update(
                    {
                        "status": "completed",
                        "end_time": current_time,
                        "outputs": outputs,
                    }
                )
                break
        else:
            # Step missing (edge case) – add completed step
            step = {
                "id": step_id,
                "name": event.method_name,
                "status": "completed",
                "start_time": current_time,
                "end_time": current_time,
                "outputs": outputs,
            }
            flow_state["steps"].append(step)

        flow_state["timestamp"] = current_time

        await self.broadcast_update(
            flow_id=broadcast_flow_id, flow_state=flow_state, update_type="flow_state"
        )

    async def _handle_method_failed(self, flow_id: str, event):
        """Handle method execution failed event asynchronously."""
        logger.info(f"Method failed: {flow_id}, method: {event.method_name}")

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "method_failed"
        )

        current_time = asyncio.get_event_loop().time()
        step_id = event.method_name
        error_msg = getattr(event, "error", None)

        for step in flow_state["steps"]:
            if step["id"] == step_id and step.get("status") == "running":
                step.update(
                    {
                        "status": "failed",
                        "end_time": current_time,
                        "error": str(error_msg) if error_msg else "Unknown error",
                    }
                )
                break
        else:
            # Missing step – add failed step entry
            step = {
                "id": step_id,
                "name": event.method_name,
                "status": "failed",
                "start_time": current_time,
                "end_time": current_time,
                "error": str(error_msg) if error_msg else "Unknown error",
            }
            flow_state["steps"].append(step)

        flow_state["timestamp"] = current_time

        await self.broadcast_update(
            flow_id=broadcast_flow_id, flow_state=flow_state, update_type="flow_state"
        )

    async def _handle_crew_kickoff_started_crew(self, execution_id: str, event):
        """Handle crew kickoff started event for crew context."""
        from .entities import entity_service
        
        logger.info(f"🚀 Crew kickoff started - execution_id: {execution_id}")

        # Extract crew information from the event
        crew_id = getattr(event, "crew_id", execution_id)
        crew_name = getattr(event, "crew_name", "Unknown Crew")
        
        # Register the crew entity with the entity service
        entity_service.register_entity(
            primary_id=execution_id,  # Use execution_id as primary
            internal_id=crew_id if crew_id != execution_id else None,
            entity_type="crew",
            name=crew_name
        )
        logger.debug(f"Registered crew entity: primary_id={execution_id}, internal_id={crew_id}, name={crew_name}")

        # Initialize crew state
        self.crew_state = {
            "id": crew_id,
            "name": crew_name,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "type": getattr(event, "process", "sequential"),
        }

        # Initialize agent and task states
        self.agent_states.clear()
        self.task_states.clear()

        # Try to extract initial agent and task information if available
        if hasattr(event, "crew") and event.crew:
            crew = event.crew

            # Extract agents with improved ID consistency
            if hasattr(crew, "agents") and crew.agents:
                for i, agent in enumerate(crew.agents):
                    # Use consistent ID extraction
                    agent_id = getattr(agent, "id", None)
                    if not agent_id and hasattr(agent, "role"):
                        # Create hash-based ID from role for consistency
                        role_hash = abs(hash(agent.role)) % 100000
                        agent_id = f"agent_{role_hash}"
                    elif not agent_id:
                        agent_id = f"agent_{i}"
                    else:
                        agent_id = str(agent_id)
                    
                    self.agent_states[agent_id] = {
                        "id": agent_id,
                        "name": getattr(agent, "name", f"Agent {i+1}"),
                        "role": getattr(agent, "role", "Unknown"),
                        "status": "initializing",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    
                    # Add optional rich data if available
                    if hasattr(agent, "description") and agent.description:
                        self.agent_states[agent_id]["description"] = agent.description
                    if hasattr(agent, "backstory") and agent.backstory:
                        self.agent_states[agent_id]["backstory"] = agent.backstory
                    if hasattr(agent, "goal") and agent.goal:
                        self.agent_states[agent_id]["goal"] = agent.goal

            # Extract tasks with improved ID consistency and agent association
            if hasattr(crew, "tasks") and crew.tasks:
                for i, task in enumerate(crew.tasks):
                    # Use consistent ID extraction
                    task_id = getattr(task, "id", None)
                    if not task_id and hasattr(task, "description"):
                        # Create hash-based ID from description for consistency
                        desc_hash = abs(hash(task.description[:50])) % 100000
                        task_id = f"task_{desc_hash}"
                    elif not task_id:
                        task_id = f"task_{i}"
                    else:
                        task_id = str(task_id)
                    
                    # Extract agent ID with consistent mapping
                    agent_id = None
                    if hasattr(task, "agent_id") and task.agent_id:
                        agent_id = str(task.agent_id)
                    elif hasattr(task, "agent") and task.agent:
                        if hasattr(task.agent, "id"):
                            agent_id = str(task.agent.id)
                        elif hasattr(task.agent, "role"):
                            # Use same hash-based ID as agents
                            role_hash = abs(hash(task.agent.role)) % 100000
                            agent_id = f"agent_{role_hash}"
                    
                    self.task_states[task_id] = {
                        "id": task_id,
                        "name": getattr(task, "name", f"Task {i+1}"),
                        "description": getattr(task, "description", f"Task {i+1}"),
                        "status": "pending",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    
                    # Add agent association if found
                    if agent_id:
                        self.task_states[task_id]["agent_id"] = agent_id
                    
                    # Add optional rich data if available
                    if hasattr(task, "expected_output") and task.expected_output:
                        self.task_states[task_id]["expected_output"] = task.expected_output

        logger.info(
            f"Initialized crew state: {len(self.agent_states)} agents, "
            f"{len(self.task_states)} tasks"
        )
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
                logger.info(
                    f"Crew result stored as output: {self.crew_state.get('output', 'No output')[:100]}..."
                )

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

        # Extract consistent agent ID
        agent_id = self._extract_agent_id(event)
        
        # Extract comprehensive agent data
        agent_data = self._extract_agent_data(event)
        
        # Preserve existing agent data if available, otherwise create new
        if agent_id in self.agent_states:
            # Update existing agent state while preserving rich data
            existing_agent = self.agent_states[agent_id]
            self.agent_states[agent_id].update({
                "status": "running",
                "timestamp": datetime.utcnow().isoformat(),
            })
            
            # Only update fields if we have better data from the event
            if agent_data.get("name") and agent_data["name"] != existing_agent.get("name"):
                self.agent_states[agent_id]["name"] = agent_data["name"]
            if agent_data.get("role") and agent_data["role"] != existing_agent.get("role"):
                self.agent_states[agent_id]["role"] = agent_data["role"]
            if agent_data.get("description") and not existing_agent.get("description"):
                self.agent_states[agent_id]["description"] = agent_data["description"]
                
            logger.info(f"Updated existing agent {agent_id}: {self.agent_states[agent_id].get('name', 'Unknown')}")
        else:
            # Create new agent state with extracted data
            self.agent_states[agent_id] = {
                "id": agent_id,
                "name": agent_data.get("name") or f"Agent {agent_id}",
                "role": agent_data.get("role") or "Unknown",
                "status": "running",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            # Add optional fields if available
            if agent_data.get("description"):
                self.agent_states[agent_id]["description"] = agent_data["description"]
            if agent_data.get("backstory"):
                self.agent_states[agent_id]["backstory"] = agent_data["backstory"]
            if agent_data.get("goal"):
                self.agent_states[agent_id]["goal"] = agent_data["goal"]
                
            logger.info(f"Created new agent {agent_id}: {self.agent_states[agent_id]['name']}")

        await self.broadcast_update()

    async def _handle_agent_execution_completed_crew(self, execution_id: str, event):
        """Handle agent execution completed event in crew context."""
        logger.info(
            f"Agent execution completed (crew context) for execution: {execution_id}"
        )

        # Extract consistent agent ID
        agent_id = self._extract_agent_id(event)
        
        # Extract any additional agent data from the completion event
        agent_data = self._extract_agent_data(event)

        if agent_id in self.agent_states:
            # Update existing agent state
            self.agent_states[agent_id].update(
                {
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            # Add result if available
            if hasattr(event, "result") and event.result is not None:
                self.agent_states[agent_id]["result"] = str(event.result)
            elif hasattr(event, "output") and event.output is not None:
                self.agent_states[agent_id]["result"] = str(event.output)
                
            # Update any missing data from the completion event
            if agent_data.get("name") and not self.agent_states[agent_id].get("name", "").startswith("Agent "):
                self.agent_states[agent_id]["name"] = agent_data["name"]
            if agent_data.get("role") and self.agent_states[agent_id].get("role") == "Unknown":
                self.agent_states[agent_id]["role"] = agent_data["role"]
            if agent_data.get("description") and not self.agent_states[agent_id].get("description"):
                self.agent_states[agent_id]["description"] = agent_data["description"]
                
            logger.info(f"Agent {agent_id} completed: {self.agent_states[agent_id].get('name', 'Unknown')}")
        else:
            # Create agent state if it doesn't exist (edge case)
            logger.warning(f"Agent {agent_id} completed but no initial state found, creating new state")
            self.agent_states[agent_id] = {
                "id": agent_id,
                "name": agent_data.get("name") or f"Agent {agent_id}",
                "role": agent_data.get("role") or "Unknown",
                "status": "completed",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            # Add optional fields if available
            if agent_data.get("description"):
                self.agent_states[agent_id]["description"] = agent_data["description"]
            if hasattr(event, "result") and event.result is not None:
                self.agent_states[agent_id]["result"] = str(event.result)
            elif hasattr(event, "output") and event.output is not None:
                self.agent_states[agent_id]["result"] = str(event.output)

        await self.broadcast_update()

    async def _handle_agent_execution_error_crew(self, execution_id: str, event):
        """Handle agent execution error event in crew context."""
        logger.info(
            f"Agent execution error (crew context) for execution: {execution_id}"
        )

        # Extract consistent agent ID
        agent_id = self._extract_agent_id(event)
        
        # Extract any additional agent data from the error event
        agent_data = self._extract_agent_data(event)

        if agent_id in self.agent_states:
            # Update existing agent state
            self.agent_states[agent_id].update(
                {
                    "status": "failed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            # Add error information if available
            if hasattr(event, "error") and event.error is not None:
                self.agent_states[agent_id]["error"] = str(event.error)
            elif hasattr(event, "exception") and event.exception is not None:
                self.agent_states[agent_id]["error"] = str(event.exception)
                
            # Update any missing data from the error event
            if agent_data.get("name") and not self.agent_states[agent_id].get("name", "").startswith("Agent "):
                self.agent_states[agent_id]["name"] = agent_data["name"]
            if agent_data.get("role") and self.agent_states[agent_id].get("role") == "Unknown":
                self.agent_states[agent_id]["role"] = agent_data["role"]
            if agent_data.get("description") and not self.agent_states[agent_id].get("description"):
                self.agent_states[agent_id]["description"] = agent_data["description"]
                
            logger.error(f"Agent {agent_id} failed: {self.agent_states[agent_id].get('name', 'Unknown')}")
        else:
            # Create agent state if it doesn't exist (edge case)
            logger.warning(f"Agent {agent_id} failed but no initial state found, creating new state")
            self.agent_states[agent_id] = {
                "id": agent_id,
                "name": agent_data.get("name") or f"Agent {agent_id}",
                "role": agent_data.get("role") or "Unknown",
                "status": "failed",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            # Add optional fields if available
            if agent_data.get("description"):
                self.agent_states[agent_id]["description"] = agent_data["description"]
            if hasattr(event, "error") and event.error is not None:
                self.agent_states[agent_id]["error"] = str(event.error)
            elif hasattr(event, "exception") and event.exception is not None:
                self.agent_states[agent_id]["error"] = str(event.exception)

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

        # Extract consistent task ID
        task_id = self._extract_task_id(event)
        
        # Extract comprehensive task data
        task_data = self._extract_task_data(event)

        # Preserve existing task data if available, otherwise create new
        if task_id in self.task_states:
            # Update existing task state while preserving rich data
            existing_task = self.task_states[task_id]
            self.task_states[task_id].update({
                "status": "running",
                "timestamp": datetime.utcnow().isoformat(),
            })
            
            # Only update fields if we have better data from the event
            if task_data.get("name") and task_data["name"] != existing_task.get("name"):
                self.task_states[task_id]["name"] = task_data["name"]
            if task_data.get("description") and not existing_task.get("description"):
                self.task_states[task_id]["description"] = task_data["description"]
            if task_data.get("agent_id") and not existing_task.get("agent_id"):
                self.task_states[task_id]["agent_id"] = task_data["agent_id"]
                
            logger.info(f"Updated existing task {task_id}: {self.task_states[task_id].get('name', 'Unknown')}")
        else:
            # Create new task state with extracted data
            self.task_states[task_id] = {
                "id": task_id,
                "name": task_data.get("name") or f"Task {task_id}",
                "description": task_data.get("description") or "",
                "status": "running",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            # Add optional fields if available
            if task_data.get("agent_id"):
                self.task_states[task_id]["agent_id"] = task_data["agent_id"]
            if task_data.get("expected_output"):
                self.task_states[task_id]["expected_output"] = task_data["expected_output"]
                
            logger.info(f"Created new task {task_id}: {self.task_states[task_id]['name']}")

        await self.broadcast_update()

    async def _handle_task_completed_crew(self, execution_id: str, event):
        """Handle task completed event in crew context."""
        logger.info(f"Task completed (crew context) for execution: {execution_id}")

        # Extract consistent task ID
        task_id = self._extract_task_id(event)
        
        # Extract any additional task data from the completion event
        task_data = self._extract_task_data(event)

        if task_id in self.task_states:
            # Update existing task state
            self.task_states[task_id].update(
                {
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            # Add result if available
            if hasattr(event, "result") and event.result is not None:
                self.task_states[task_id]["result"] = str(event.result)
            elif hasattr(event, "output") and event.output is not None:
                self.task_states[task_id]["result"] = str(event.output)
                
            # Update any missing data from the completion event
            if task_data.get("name") and not self.task_states[task_id].get("name", "").startswith("Task "):
                self.task_states[task_id]["name"] = task_data["name"]
            if task_data.get("description") and not self.task_states[task_id].get("description"):
                self.task_states[task_id]["description"] = task_data["description"]
            if task_data.get("agent_id") and not self.task_states[task_id].get("agent_id"):
                self.task_states[task_id]["agent_id"] = task_data["agent_id"]
                
            logger.info(f"Task {task_id} completed: {self.task_states[task_id].get('name', 'Unknown')}")
        else:
            # Create task state if it doesn't exist (edge case)
            logger.warning(f"Task {task_id} completed but no initial state found, creating new state")
            self.task_states[task_id] = {
                "id": task_id,
                "name": task_data.get("name") or f"Task {task_id}",
                "description": task_data.get("description") or "",
                "status": "completed",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            # Add optional fields if available
            if task_data.get("agent_id"):
                self.task_states[task_id]["agent_id"] = task_data["agent_id"]
            if hasattr(event, "result") and event.result is not None:
                self.task_states[task_id]["result"] = str(event.result)
            elif hasattr(event, "output") and event.output is not None:
                self.task_states[task_id]["result"] = str(event.output)

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
