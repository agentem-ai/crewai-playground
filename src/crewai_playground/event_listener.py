import logging
from typing import Dict, List, Any, Optional
import json
import asyncio
from datetime import datetime
from fastapi import WebSocket
from crewai.utilities.events import (
    CrewKickoffStartedEvent,
    CrewKickoffCompletedEvent,
    AgentExecutionStartedEvent,
    AgentExecutionCompletedEvent,
    TaskStartedEvent,
    TaskCompletedEvent,
    LLMCallStartedEvent,
    LLMCallCompletedEvent,
)
from crewai_playground.events import (
    CrewInitializationRequestedEvent,
    CrewInitializationCompletedEvent,
)
from crewai_playground.telemetry import telemetry_service
from crewai.utilities.events.base_event_listener import BaseEventListener

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Custom JSON encoder to handle datetime objects and other custom types
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle TaskOutput objects
        if hasattr(obj, "__dict__"):
            return str(obj)
        # Try to convert to string if all else fails
        try:
            return str(obj)
        except:
            return "[Unserializable Object]"
        return super().default(obj)


class CrewVisualizationListener(BaseEventListener):
    """Event listener for visualizing crew execution in the UI."""

    def __init__(self):
        self._registered_buses = set()
        super().__init__()
        # Replace simple connection list with client dictionary
        self.clients = {}  # client_id -> {websocket, crew_id, connected_at, last_ping}
        self.crew_state: Dict[str, Any] = {}
        self.agent_states: Dict[str, Dict[str, Any]] = {}
        self.task_states: Dict[str, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, client_id: str, crew_id: str = None):
        """Connect a new WebSocket client."""
        # Capture the running loop so we can schedule updates from sync event callbacks
        self.loop = asyncio.get_running_loop()

        await websocket.accept()
        self.clients[client_id] = {
            "websocket": websocket,
            "crew_id": crew_id,
            "connected_at": datetime.utcnow(),
            "last_ping": datetime.utcnow()
        }
        logger.info(
            f"WebSocket client {client_id} connected. Total connections: {len(self.clients)}"
        )
        # If crew_id provided, send current state for that crew
        if crew_id and self.crew_state and self.crew_state.get("id") == crew_id:
            logger.info(f"Sending initial state to new client for crew {crew_id}")
            await self.send_state_to_client(client_id)

    def disconnect(self, client_id: str):
        """Disconnect a client by ID."""
        if client_id in self.clients:
            del self.clients[client_id]
            logger.info(
                f"WebSocket client {client_id} disconnected. Remaining connections: {len(self.clients)}"
            )
            
    async def register_client_for_crew(self, client_id: str, crew_id: str):
        """Register a client for updates from a specific crew."""
        if client_id in self.clients:
            self.clients[client_id]["crew_id"] = crew_id
            logger.info(f"Client {client_id} registered for crew {crew_id}")
            await self.send_state_to_client(client_id)
    
    async def send_state_to_client(self, client_id: str):
        """Send current state to a specific client."""
        if client_id not in self.clients:
            return
            
        client = self.clients[client_id]
        websocket = client["websocket"]
        crew_id = client["crew_id"]
        
        # Only send state for the client's registered crew
        if crew_id and self.crew_state and self.crew_state.get("id") == crew_id:
            try:
                state = {
                    "crew": self.crew_state,
                    "agents": list(self.agent_states.values()),
                    "tasks": list(self.task_states.values())
                }
                # Use CustomJSONEncoder to handle datetime and other complex objects
                json_data = json.dumps(state, cls=CustomJSONEncoder)
                await websocket.send_text(json_data)
                logger.debug(f"Sent state to client {client_id} for crew {crew_id}")
            except Exception as e:
                logger.error(f"Error sending state to client {client_id}: {str(e)}")
                self.disconnect(client_id)

    async def broadcast_update(self):
        """Broadcast the current state to all connected WebSocket clients."""
        if not self.clients:
            logger.info("No active connections to broadcast to")
            return

        crew_id = self.crew_state.get("id") if self.crew_state else None
        logger.info(f"Broadcasting update for crew {crew_id} to {len(self.clients)} clients")
        
        for client_id, client in list(self.clients.items()):
            client_crew_id = client.get("crew_id")
            # Only broadcast to clients registered for this crew or with no specific crew
            if not client_crew_id or (crew_id and client_crew_id == crew_id):
                try:
                    websocket = client["websocket"]
                    state = {
                        "crew": self.crew_state,
                        "agents": list(self.agent_states.values()),
                        "tasks": list(self.task_states.values()),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    # Use CustomJSONEncoder to handle datetime and other complex objects
                    json_data = json.dumps(state, cls=CustomJSONEncoder)
                    await websocket.send_text(json_data)
                    logger.debug(f"Sent update to client {client_id} for crew {crew_id}")
                except Exception as e:
                    logger.error(f"Error broadcasting to client {client_id}: {str(e)}")
                    self.disconnect(client_id)

    def reset_state(self):
        """Reset the state when a new crew execution starts."""
        self.crew_state = {}
        self.agent_states = {}
        self.task_states = {}
        logger.info("State reset for new crew execution")

    def setup_listeners(self, crewai_event_bus):
        """Set up event listeners for crew visualization."""
        bus_id = id(crewai_event_bus)
        if bus_id in self._registered_buses:
            logger.info(f"Listeners already set up for event bus {bus_id}.")
            return

        logger.info(f"Setting up new listeners for event bus {bus_id}")
        self._registered_buses.add(bus_id)
        
        @crewai_event_bus.on(CrewInitializationRequestedEvent)
        def on_crew_initialization_requested(source, event):
            """Handle crew initialization request."""
            crew_id = event.crew_id
            logger.info(f"Crew initialization requested for {event.crew_name} (ID: {crew_id})")
            
            # Reset state for new initialization
            self.reset_state()
            
            # Store crew information
            self.crew_state = {
                "id": crew_id,
                "name": event.crew_name,
                "status": "initializing",
                "started_at": event.timestamp or datetime.utcnow(),
            }
            
            # Schedule async broadcast
            if hasattr(self, "loop"):
                asyncio.run_coroutine_threadsafe(self.broadcast_update(), self.loop)
        
        @crewai_event_bus.on(CrewInitializationCompletedEvent)
        def on_crew_initialization_completed(source, event):
            """Handle crew initialization completion."""
            crew_id = event.crew_id
            logger.info(f"Crew initialization completed for {event.crew_name} (ID: {crew_id})")
            
            # Update crew state
            self.crew_state = {
                "id": crew_id,
                "name": event.crew_name,
                "status": "ready",
                "initialized_at": event.timestamp or datetime.utcnow(),
            }
            
            # Initialize agent states
            for agent in event.agents:
                agent_id = agent.get("id")
                if agent_id:
                    self.agent_states[agent_id] = agent
                    logger.debug(f"Added agent {agent_id} to state")
            
            # Initialize task states
            for task in event.tasks:
                task_id = task.get("id")
                if task_id:
                    self.task_states[task_id] = task
                    logger.debug(f"Added task {task_id} to state")
            
            # Schedule async broadcast
            if hasattr(self, "loop"):
                asyncio.run_coroutine_threadsafe(self.broadcast_update(), self.loop)

        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def on_crew_kickoff_started(source, event):
            logger.info(f"Crew '{event.crew_name}' execution started")

            # Reset state for new execution
            self.reset_state()

            # Get crew ID - ensure it's a string and normalize it
            crew_id = str(source.id) if hasattr(source, "id") else "unknown"

            # Log the crew ID for debugging
            logger.info(f"CrewKickoffStartedEvent - Using crew_id: {crew_id}")

            # Store crew information
            self.crew_state = {
                "id": crew_id,
                "name": event.crew_name,
                "status": "running",
                "started_at": (
                    event.timestamp.isoformat()
                    if isinstance(event.timestamp, datetime)
                    else event.timestamp
                ),
            }

            # Start a new trace in telemetry
            telemetry_service.start_crew_trace(crew_id, event.crew_name)

            # Store agent information
            for agent in source.agents:
                agent_id = (
                    str(agent.id)
                    if hasattr(agent, "id")
                    else f"agent_{len(self.agent_states)}"
                )
                self.agent_states[agent_id] = {
                    "id": agent_id,
                    "role": agent.role,
                    "name": agent.name if hasattr(agent, "name") else agent.role,
                    "status": "waiting",
                    "description": (
                        agent.backstory[:100] + "..."
                        if len(agent.backstory) > 100
                        else agent.backstory
                    ),
                }

            # Store task information if available and associate with agents
            if hasattr(source, "tasks"):
                # First, collect all agents by role for matching
                agent_by_role = {}
                agent_by_id = {}
                for agent in source.agents:
                    agent_id = str(agent.id) if hasattr(agent, "id") else None
                    if agent_id:
                        agent_by_id[agent_id] = agent
                        role_key = agent.role.lower() if hasattr(agent, "role") else ""
                        agent_by_role[role_key] = agent_id

                # Process tasks and try to associate them with agents
                for i, task in enumerate(source.tasks):
                    task_id = str(task.id) if hasattr(task, "id") else f"task_{i}"
                    task_desc = (
                        task.description.lower() if hasattr(task, "description") else ""
                    )

                    # Try to find an agent for this task
                    assigned_agent_id = None

                    # First check if task already has an agent assigned
                    if hasattr(task, "agent") and task.agent:
                        agent_id = (
                            str(task.agent.id) if hasattr(task.agent, "id") else None
                        )
                        if agent_id:
                            assigned_agent_id = agent_id

                    # If no agent is assigned, try to match based on task description and agent roles
                    if not assigned_agent_id:
                        # Try to match based on keywords in task description and agent roles
                        best_match = None
                        best_match_score = 0

                        for role, agent_id in agent_by_role.items():
                            # Skip empty roles
                            if not role:
                                continue

                            # Calculate a simple matching score
                            role_words = set(role.split())
                            task_words = set(task_desc.split())

                            # Count matching significant words (longer than 3 chars)
                            match_score = sum(
                                1 for word in role_words & task_words if len(word) > 3
                            )

                            # Special case handling for common patterns
                            if "research" in role and "research" in task_desc:
                                match_score += 3
                            if "analyst" in role and any(
                                kw in task_desc for kw in ["analyz", "review", "report"]
                            ):
                                match_score += 3

                            if match_score > best_match_score:
                                best_match_score = match_score
                                best_match = agent_id

                        # If we found a reasonable match, assign the task to this agent
                        if best_match_score > 0:
                            assigned_agent_id = best_match
                        # If we still don't have a match but there's only one agent, assign to it
                        elif len(agent_by_id) == 1:
                            assigned_agent_id = next(iter(agent_by_id.keys()))
                        # If we have exactly two agents and can identify researcher/analyst pattern
                        elif len(agent_by_id) == 2:
                            # For a research task, assign to the first agent
                            if "research" in task_desc:
                                assigned_agent_id = list(agent_by_id.keys())[0]
                            # For a reporting/analysis task, assign to the second agent
                            elif any(
                                kw in task_desc
                                for kw in ["report", "analyz", "review", "summarize"]
                            ):
                                assigned_agent_id = list(agent_by_id.keys())[1]

                    # Store the task with its assigned agent (if any)
                    self.task_states[task_id] = {
                        "id": task_id,
                        "description": (
                            task.description if hasattr(task, "description") else ""
                        ),
                        "status": "pending",
                        "agent_id": assigned_agent_id,
                    }

            # Broadcast the update asynchronously
            # Schedule the broadcast on the main event loop
            if hasattr(self, "loop"):
                asyncio.run_coroutine_threadsafe(self.broadcast_update(), self.loop)

        @crewai_event_bus.on(AgentExecutionStartedEvent)
        def on_agent_execution_started(source, event):
            agent = event.agent
            agent_id = str(agent.id) if hasattr(agent, "id") else None

            if agent_id and agent_id in self.agent_states:
                logger.info(f"Agent '{agent.role}' started execution")

                # Update agent status
                self.agent_states[agent_id]["status"] = "running"

                # Get crew ID
                crew_id = self.crew_state.get("id")
                if crew_id:
                    # Record in telemetry
                    telemetry_service.start_agent_execution(
                        crew_id=crew_id,
                        agent_id=agent_id,
                        agent_name=agent.name if hasattr(agent, "name") else agent.role,
                        agent_role=agent.role,
                    )

                # If there's a task associated with this execution, update it
                if hasattr(event, "task"):
                    task = event.task
                    task_id = str(task.id) if hasattr(task, "id") else None

                    if task_id and task_id in self.task_states:
                        self.task_states[task_id]["status"] = "running"
                        self.task_states[task_id]["agent_id"] = agent_id

                # Broadcast the update asynchronously
                # Schedule the broadcast on the main event loop
            if hasattr(self, "loop"):
                asyncio.run_coroutine_threadsafe(self.broadcast_update(), self.loop)

        @crewai_event_bus.on(AgentExecutionCompletedEvent)
        def on_agent_execution_completed(source, event):
            agent = event.agent
            agent_id = str(agent.id) if hasattr(agent, "id") else None

            if agent_id and agent_id in self.agent_states:
                logger.info(f"Agent '{agent.role}' completed execution")

                # Update agent status
                self.agent_states[agent_id]["status"] = "completed"

                # Get crew ID
                crew_id = self.crew_state.get("id")
                if crew_id:
                    # Record in telemetry
                    telemetry_service.end_agent_execution(
                        crew_id=crew_id,
                        agent_id=agent_id,
                        output=event.output if hasattr(event, "output") else None,
                    )

                # If there's a task associated with this execution, update it
                if hasattr(event, "task"):
                    task = event.task
                    task_id = str(task.id) if hasattr(task, "id") else None

                    if task_id and task_id in self.task_states:
                        self.task_states[task_id]["status"] = "completed"

                # Broadcast the update asynchronously
                # Schedule the broadcast on the main event loop
            if hasattr(self, "loop"):
                asyncio.run_coroutine_threadsafe(self.broadcast_update(), self.loop)

        @crewai_event_bus.on(TaskStartedEvent)
        def on_task_started(source, event):
            task = event.task
            task_id = str(task.id) if hasattr(task, "id") else None

            if task_id:
                logger.info(f"Task '{task.description[:30]}...' started")

                # Get crew ID
                crew_id = self.crew_state.get("id")
                if crew_id:
                    # Get agent ID if available
                    agent_id = None
                    if hasattr(task, "agent") and task.agent:
                        agent_id = (
                            str(task.agent.id) if hasattr(task.agent, "id") else None
                        )

                    # Record in telemetry
                    telemetry_service.start_task_execution(
                        crew_id=crew_id,
                        task_id=task_id,
                        task_description=(
                            task.description if hasattr(task, "description") else ""
                        ),
                        agent_id=agent_id,
                    )

                # Add task to state if it doesn't exist
                if task_id not in self.task_states:
                    self.task_states[task_id] = {
                        "id": task_id,
                        "description": (
                            task.description if hasattr(task, "description") else ""
                        ),
                        "status": "running",
                        "agent_id": None,
                    }
                else:
                    self.task_states[task_id]["status"] = "running"

                # If there's an agent assigned to this task, update it
                agent_id = None

                # First check if task has an agent directly assigned
                if hasattr(task, "agent") and task.agent:
                    agent = task.agent
                    agent_id = str(agent.id) if hasattr(agent, "id") else None

                # If no agent is directly assigned, check if the source is an agent
                if not agent_id and hasattr(source, "id") and hasattr(source, "role"):
                    # The source might be the agent executing this task
                    agent_id = str(source.id)

                # If we found an agent ID, update the task and agent states
                if agent_id:
                    # Update task with agent ID
                    self.task_states[task_id]["agent_id"] = agent_id

                    # Also update agent status if it exists
                    if agent_id in self.agent_states:
                        self.agent_states[agent_id]["status"] = "running"

                        # Log the association
                        agent_name = self.agent_states[agent_id].get(
                            "name", "Unknown agent"
                        )
                        logger.info(
                            f"Associated task '{task_id}' with agent '{agent_name}' (ID: {agent_id})"
                        )

                # Broadcast the update asynchronously
                # Schedule the broadcast on the main event loop
            if hasattr(self, "loop"):
                asyncio.run_coroutine_threadsafe(self.broadcast_update(), self.loop)

        @crewai_event_bus.on(TaskCompletedEvent)
        def on_task_completed(source, event):
            task = event.task
            task_id = str(task.id) if hasattr(task, "id") else None

            if task_id and task_id in self.task_states:
                logger.info(f"Task '{task.description[:30]}...' completed")

                # Update task status
                self.task_states[task_id]["status"] = "completed"

                # Get crew ID
                crew_id = self.crew_state.get("id")
                if crew_id:
                    # Record in telemetry
                    telemetry_service.end_task_execution(
                        crew_id=crew_id,
                        task_id=task_id,
                        output=event.output if hasattr(event, "output") else None,
                    )

                # Broadcast the update asynchronously
                # Schedule the broadcast on the main event loop
            if hasattr(self, "loop"):
                asyncio.run_coroutine_threadsafe(self.broadcast_update(), self.loop)

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def on_crew_kickoff_completed(source, event):
            logger.info(f"Crew '{event.crew_name}' execution completed")

            output_text = (
                event.output.raw if hasattr(event.output, "raw") else str(event.output)
            )

            # Update crew status
            self.crew_state["status"] = "completed"
            self.crew_state["completed_at"] = (
                event.timestamp.isoformat()
                if isinstance(event.timestamp, datetime)
                else event.timestamp
            )
            self.crew_state["output"] = output_text

            # Get crew ID - first try from source, then from state
            crew_id = (
                str(source.id) if hasattr(source, "id") else self.crew_state.get("id")
            )

            # Log the crew ID for debugging
            logger.info(f"CrewKickoffCompletedEvent - Using crew_id: {crew_id}")

            if crew_id:
                # Record in telemetry
                telemetry_service.end_crew_trace(crew_id=crew_id, output=output_text)

            # Mark all agents and tasks as completed
            for agent_id in self.agent_states:
                self.agent_states[agent_id]["status"] = "completed"

            for task_id in self.task_states:
                self.task_states[task_id]["status"] = "completed"

            # Broadcast the update asynchronously
            # Schedule the broadcast on the main event loop
            if hasattr(self, "loop"):
                asyncio.run_coroutine_threadsafe(self.broadcast_update(), self.loop)

        # Add handlers for LLM call events

        @crewai_event_bus.on(LLMCallStartedEvent)
        def on_llm_call_started(source, event):
            # Get the crew ID
            crew_id = self.crew_state.get("id")
            if not crew_id:
                return

            # Get the agent ID if available
            agent_id = None
            if hasattr(event, "agent") and event.agent:
                agent_id = str(event.agent.id) if hasattr(event.agent, "id") else None

            # Log the event
            logger.info(f"LLM call started")

            # Add an event to telemetry
            telemetry_service.add_event(
                crew_id=crew_id,
                event_type="llm.started",
                event_data={
                    "agent_id": agent_id,
                    "prompt": event.prompt if hasattr(event, "prompt") else "",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        @crewai_event_bus.on(LLMCallCompletedEvent)
        def on_llm_call_completed(source, event):
            # Get the crew ID
            crew_id = self.crew_state.get("id")
            if not crew_id:
                return

            # Get the agent ID if available
            agent_id = None
            if hasattr(event, "agent") and event.agent:
                agent_id = str(event.agent.id) if hasattr(event.agent, "id") else None

            # Log the event
            logger.info(f"LLM call completed")

            # Add an event to telemetry
            telemetry_service.add_event(
                crew_id=crew_id,
                event_type="llm.completed",
                event_data={
                    "agent_id": agent_id,
                    "response": event.response if hasattr(event, "response") else "",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )


# Create a singleton instance
crew_visualization_listener = CrewVisualizationListener()
