import json
import logging
import os
import sys
import datetime
import uuid
from pathlib import Path
import threading
from typing import Dict, Optional, List, Any
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import click
import socket
import asyncio
import importlib
import inspect
from crewai_playground.tool_loader import discover_available_tools

# Configure logging
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Suppress Werkzeug logging
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

# Load environment variables from a .env file if present
try:
    from dotenv import load_dotenv, find_dotenv

    env_path = find_dotenv(usecwd=True)
    if env_path:
        load_dotenv(env_path, override=False)
        logging.getLogger(__name__).info(
            "Environment variables loaded from %s", env_path
        )
    else:
        logging.getLogger(__name__).warning(
            "No .env file found when initialising server"
        )
except ImportError:
    # python-dotenv not installed; proceed without loading
    pass

from crewai_playground.crew_loader import (
    load_crew,
    load_crew_from_module,
    discover_available_crews,
)
from crewai_playground.chat_handler import ChatHandler
from crewai_playground.event_listener import crew_visualization_listener
from crewai_playground.tool_loader import discover_available_tools as discover_tools
from crewai_playground.telemetry import telemetry_service
from crewai_playground.flow_api import (
    router as flow_router,
    get_active_execution,
    FlowInfo,
    flows_cache,
    active_flows,
    is_execution_active,
)
from crewai_playground.websocket_utils import (
    register_websocket_queue,
    unregister_websocket_queue,
)
from crewai_playground.flow_event_listener import flow_websocket_listener
from crewai.utilities.events import crewai_event_bus
from crewai.utilities.events.agent_events import (
    AgentEvaluationStartedEvent,
    AgentEvaluationCompletedEvent,
    AgentEvaluationFailedEvent,
)

# CrewAI Evaluation imports
try:
    from crewai.experimental.evaluation import (
        AgentEvaluator,
        create_default_evaluator,
        BaseEvaluator,
        MetricCategory,
        EvaluationScore,
        AgentEvaluationResult,
        EvaluationTraceCallback,
        create_evaluation_callbacks,
    )

    EVALUATION_AVAILABLE = True

    # Simple aggregation strategy enum since it's not available in the module
    class AggregationStrategy:
        SIMPLE_AVERAGE = "simple_average"
        WEIGHTED_BY_COMPLEXITY = "weighted_by_complexity"
        BEST_PERFORMANCE = "best_performance"
        WORST_PERFORMANCE = "worst_performance"

except ImportError:
    logging.warning(
        "CrewAI evaluation module not available. Evaluation features will be disabled."
    )
    EVALUATION_AVAILABLE = False

    # Fallback aggregation strategy for when evaluation is not available
    class AggregationStrategy:
        SIMPLE_AVERAGE = "simple_average"
        WEIGHTED_BY_COMPLEXITY = "weighted_by_complexity"
        BEST_PERFORMANCE = "best_performance"
        WORST_PERFORMANCE = "worst_performance"


# Create FastAPI app
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the flow API router
app.include_router(flow_router)


# Dashboard API endpoint
@app.get("/api/dashboard")
async def get_dashboard_data():
    """Get dashboard data including counts of crews, tools, and flows."""
    try:
        # Get counts of available resources
        crews_count = len(discovered_crews)
        tools_count = len(discover_tools())
        flows_count = len(flows_cache)

        # Get recent traces
        recent_traces = telemetry_service.get_traces(limit=5)

        # Get active flows
        active_flow_data = [
            {
                "id": flow_id,
                "name": flows_cache.get(
                    flow_id,
                    FlowInfo(
                        id=flow_id,
                        name="Unknown",
                        description="",
                        file_path="",
                        class_name="",
                        flow_class=None,
                    ),
                ).name,
                "status": state.get("status", "unknown"),
                "start_time": state.get("timestamp", 0),
            }
            for flow_id, state in active_flows.items()
        ]

        return {
            "status": "success",
            "data": {
                "counts": {
                    "crews": crews_count,
                    "tools": tools_count,
                    "flows": flows_count,
                },
                "recent_traces": recent_traces,
                "active_flows": active_flow_data,
            },
        }
    except Exception as e:
        logging.error(f"Error fetching dashboard data: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching dashboard data: {str(e)}"
        )


# Telemetry API endpoints
@app.get("/api/traces")
async def get_traces(limit: int = 10):
    """Get the most recent traces."""
    return telemetry_service.get_traces(limit=limit)


@app.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Get a specific trace by ID."""
    trace = telemetry_service.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@app.get("/api/crews/{crew_id}/traces")
async def get_crew_traces(crew_id: str):
    """Get all traces for a specific crew."""
    logging.info(f"API: Fetching traces for crew_id: {crew_id}")

    # Debug: Check what traces are available
    all_traces = telemetry_service.get_traces(limit=100)
    logging.info(f"API: Total traces available: {len(all_traces)}")

    # Get traces for this specific crew
    crew_traces = telemetry_service.get_traces_for_crew(crew_id)
    logging.info(f"API: Found {len(crew_traces)} traces for crew_id: {crew_id}")

    return crew_traces


# Get the directory containing the built React app
ui_dir = Path(__file__).parent.parent.parent / "src" / "crewai_playground" / "ui" / "build" / "client"

# Mount the static files from the React build
app.mount("/assets", StaticFiles(directory=str(ui_dir / "assets"), html=True), name="assets")

# Global state
chat_handler = None
chat_handlers: Dict[str, ChatHandler] = {}
chat_threads: Dict[str, Dict[str, List]] = {}
discovered_crews: List[Dict] = []

# Evaluation state
evaluation_runs: Dict[str, Dict] = {}
active_evaluations: Dict[str, Any] = {}
evaluation_results: Dict[str, Dict] = {}


# Pydantic models for request/response validation
class ChatMessage(BaseModel):
    message: str
    crew_id: Optional[str] = None
    chat_id: Optional[str] = None


class InitializeRequest(BaseModel):
    crew_id: Optional[str] = None
    chat_id: Optional[str] = None


class KickoffRequest(BaseModel):
    inputs: Optional[Dict[str, str]] = None


class ToolExecuteRequest(BaseModel):
    inputs: Optional[Dict[str, str]] = None


# Evaluation API models
class EvaluationConfigRequest(BaseModel):
    name: str
    crew_ids: List[str]
    metric_categories: Optional[List[str]] = None
    iterations: Optional[int] = 1
    aggregation_strategy: Optional[str] = "simple_average"
    test_inputs: Optional[Dict[str, Any]] = None


class EvaluationRunResponse(BaseModel):
    id: str
    name: str
    status: str
    progress: float
    start_time: str
    end_time: Optional[str] = None
    agent_count: int
    metric_count: int
    overall_score: Optional[float] = None
    iterations: int


@app.post("/api/chat")
async def chat(message: ChatMessage) -> JSONResponse:
    """API endpoint to handle chat messages."""
    global chat_handler

    user_message = message.message
    crew_id = message.crew_id
    chat_id = message.chat_id
    logging.debug(f"Received chat message for chat_id: {chat_id}, crew_id: {crew_id}")

    if not user_message:
        logging.warning("No message provided in request")
        raise HTTPException(status_code=400, detail="No message provided")

    try:
        # If no chat_id is provided, we can't properly track the thread
        if not chat_id:
            raise HTTPException(
                status_code=400,
                detail="No chat ID provided. Unable to track conversation thread.",
            )

        # If a specific crew_id is provided, use that chat handler
        if crew_id and crew_id in chat_handlers:
            handler = chat_handlers[crew_id]
            # Update the global chat handler to track the currently active one
            chat_handler = handler
        elif chat_handler is None:
            raise HTTPException(
                status_code=400,
                detail="No crew has been initialized. Please select a crew first.",
            )

        # Always store messages in the appropriate chat thread
        # Initialize the thread if it doesn't exist
        if chat_id not in chat_threads:
            chat_threads[chat_id] = {"crew_id": crew_id, "messages": []}
            logging.debug(f"Created new chat thread for chat_id: {chat_id}")

        # Add user message to the thread
        chat_threads[chat_id]["messages"].append(
            {"role": "user", "content": user_message}
        )
        logging.debug(
            f"Added user message to chat_id: {chat_id}, message count: {len(chat_threads[chat_id]['messages'])}"
        )

        # Always restore the conversation history for this thread
        if hasattr(chat_handler, "messages"):
            # Save the current thread first if it exists and is different
            current_thread = getattr(chat_handler, "current_chat_id", None)
            if (
                current_thread
                and current_thread != chat_id
                and hasattr(chat_handler, "messages")
            ):
                # Create a deep copy of the messages to avoid reference issues
                chat_threads[current_thread] = {
                    "crew_id": (
                        crew_id
                        if crew_id
                        else getattr(chat_handler, "crew_name", "default")
                    ),
                    "messages": (
                        chat_handler.messages.copy()
                        if isinstance(chat_handler.messages, list)
                        else []
                    ),
                }
                logging.debug(
                    f"Saved {len(chat_handler.messages)} messages from previous thread: {current_thread}"
                )

            # Restore the thread we're working with - create a deep copy to avoid reference issues
            if chat_id in chat_threads:
                chat_handler.messages = (
                    chat_threads[chat_id]["messages"].copy()
                    if isinstance(chat_threads[chat_id]["messages"], list)
                    else []
                )
                # Mark the current thread
                chat_handler.current_chat_id = chat_id
                logging.debug(
                    f"Restored {len(chat_handler.messages)} messages for chat_id: {chat_id}"
                )

        logging.debug(f"Processing message with chat_handler for chat_id: {chat_id}")
        response = chat_handler.process_message(user_message)

        # Ensure we have content in the response
        if not response.get("content") and response.get("status") == "success":
            logging.warning("Response content is empty despite successful status")
            response["content"] = (
                "I'm sorry, but I couldn't generate a response. Please try again."
            )

        # Always add the response to the chat thread if it's valid
        if response.get("status") == "success" and response.get("content"):
            # Add the assistant response to the chat thread
            chat_threads[chat_id]["messages"].append(
                {"role": "assistant", "content": response["content"]}
            )

            # Ensure chat_handler.messages is synchronized with chat_threads
            # This is critical to ensure messages are preserved correctly
            if hasattr(chat_handler, "messages"):
                # Synchronize the chat handler's messages with the thread
                chat_handler.messages = chat_threads[chat_id]["messages"].copy()

            logging.debug(
                f"Added assistant response to chat_id: {chat_id}, message count: {len(chat_threads[chat_id]['messages'])}"
            )

        # Always include the chat_id in the response to ensure proper thread tracking
        response["chat_id"] = chat_id
        response["crew_id"] = (
            crew_id if crew_id else getattr(chat_handler, "crew_name", "default")
        )
        logging.debug(
            f"Sending response for chat_id: {chat_id}, crew_id: {response['crew_id']}"
        )

        return JSONResponse(content=response)
    except Exception as e:
        error_message = f"Error processing chat message: {str(e)}"
        logging.error(error_message, exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)


@app.post("/api/initialize")
@app.get("/api/initialize")
async def initialize(request: InitializeRequest = None) -> JSONResponse:
    """Initialize the chat handler and return initial message."""
    global chat_handler

    # Handle both GET and POST requests
    crew_id = None
    chat_id = None

    if request:
        crew_id = request.crew_id
        chat_id = request.chat_id

    logging.debug(f"Initializing chat with crew_id: {crew_id}, chat_id: {chat_id}")

    try:
        # If crew_id is provided and valid, initialize that specific crew
        if crew_id:
            # If we already have this crew handler cached, use it
            if crew_id in chat_handlers:
                chat_handler = chat_handlers[crew_id]
            else:
                # Find the crew path from the discovered crews
                crew_path = None
                for crew in discovered_crews:
                    if crew.get("id") == crew_id:
                        crew_path = crew.get("path")
                        break

                if not crew_path:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Crew with ID {crew_id} not found",
                    )

                # Load and initialize the specified crew
                crew_instance, crew_name = load_crew_from_module(Path(crew_path))
                new_handler = ChatHandler(crew_instance, crew_name)
                chat_handlers[crew_id] = new_handler
                chat_handler = new_handler

        # If no chat handler is set at this point, initialize with the default
        if not chat_handler:
            # Load and initialize the first available crew
            if discovered_crews:
                crew_path = discovered_crews[0].get("path")
                crew_instance, crew_name = load_crew_from_module(Path(crew_path))
                chat_handler = ChatHandler(crew_instance, crew_name)
                chat_handlers[discovered_crews[0].get("id")] = chat_handler
            else:
                # Fall back to the original behavior
                crew_instance, crew_name = load_crew()
                chat_handler = ChatHandler(crew_instance, crew_name)

        # Initialize the chat handler
        initial_message = chat_handler.initialize()

        # If a chat_id is provided, associate it with this chat handler
        if chat_id:
            # Set the current chat ID for this handler
            chat_handler.current_chat_id = chat_id

            # If this chat thread already exists, restore its messages
            if chat_id in chat_threads:
                # Only restore if the crew matches
                if chat_threads[chat_id]["crew_id"] == crew_id:
                    # Create a deep copy of the messages to avoid reference issues
                    chat_handler.messages = (
                        chat_threads[chat_id]["messages"].copy()
                        if isinstance(chat_threads[chat_id]["messages"], list)
                        else []
                    )
                    logging.debug(
                        f"Restored {len(chat_handler.messages)} messages for chat_id: {chat_id}"
                    )
                else:
                    # If crew doesn't match, create a new thread with the same ID but different crew
                    chat_threads[chat_id] = {"crew_id": crew_id, "messages": []}
                    chat_handler.messages = []
                    logging.debug(
                        f"Created new chat thread for chat_id: {chat_id} with different crew"
                    )
            else:
                # Initialize a new chat thread
                chat_threads[chat_id] = {"crew_id": crew_id, "messages": []}
                chat_handler.messages = []
                logging.debug(f"Created new chat thread for chat_id: {chat_id}")

        return JSONResponse(
            content={
                "status": "success",
                "message": initial_message,
                "required_inputs": [
                    {"name": field.name, "description": field.description}
                    for field in chat_handler.crew_chat_inputs.inputs
                ],
                "crew_id": crew_id or chat_handler.crew_name,
                "crew_name": chat_handler.crew_name,
                "crew_description": chat_handler.crew_chat_inputs.crew_description,
                "chat_id": chat_id,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/crews")
async def get_available_crews() -> JSONResponse:
    """Get a list of all available crews."""
    return JSONResponse(content={"status": "success", "crews": discovered_crews})


@app.get("/api/tools")
async def get_available_tools() -> JSONResponse:
    """Get a list of all available tools from the CrewAI toolkit.

    Returns:
        JSONResponse with the list of available tools and their schemas
    """
    try:
        # Discover available tools
        tools_list = discover_available_tools()

        if not tools_list:
            logging.warning("No tools were discovered")

        # Process each tool to ensure all properties have descriptions
        for tool in tools_list:
            if "parameters" in tool and "properties" in tool["parameters"]:
                for prop_name, prop_schema in tool["parameters"]["properties"].items():
                    # If there's a title but no description, use the title as description
                    if "title" in prop_schema and not prop_schema.get("description"):
                        prop_schema["description"] = prop_schema["title"]
                    # If there's still no description, add a default one
                    elif not prop_schema.get("description"):
                        prop_schema["description"] = f"Parameter: {prop_name}"

        return JSONResponse(content={"status": "success", "tools": tools_list})
    except Exception as e:
        logging.error(f"Error getting available tools: {str(e)}")
        return JSONResponse(
            content={"status": "error", "message": str(e)}, status_code=500
        )


@app.post("/api/tools/{tool_name}/execute")
async def execute_tool(tool_name: str, request: ToolExecuteRequest) -> JSONResponse:
    """Execute a specific tool with the provided inputs.

    Args:
        tool_name: The name of the tool to execute
        request: The inputs for the tool

    Returns:
        JSONResponse with the tool execution results
    """
    try:
        # Get all available tools
        tools = discover_available_tools()

        # Find the requested tool
        tool_info = None
        for tool in tools:
            if tool["name"] == tool_name:
                tool_info = tool
                break

        if not tool_info:
            return JSONResponse(
                content={"status": "error", "message": f"Tool '{tool_name}' not found"},
                status_code=404,
            )

        # Import the tool class or function dynamically
        module_path = tool_info["module"]
        attr_name = tool_info["class_name"]
        is_class = tool_info.get(
            "is_class", True
        )  # Default to class-based for backward compatibility

        # Import the module
        try:
            module = importlib.import_module(module_path)
            tool_attr = getattr(module, attr_name)
        except (ImportError, AttributeError) as e:
            logging.error(f"Error importing tool: {str(e)}")
            return JSONResponse(
                content={
                    "status": "error",
                    "message": f"Error importing tool: {str(e)}",
                },
                status_code=500,
            )

        # Execute the tool based on its type
        inputs = request.inputs or {}

        if is_class:
            # Class-based tool: instantiate and call _run
            try:
                # Try instantiating with required parameters
                try:
                    # First try with name and description
                    tool_instance = tool_attr(
                        name=tool_info["name"], description=tool_info["description"]
                    )
                except Exception as name_desc_error:
                    logging.warning(
                        f"Error instantiating tool with name/description: {str(name_desc_error)}"
                    )
                    # Try with just the required parameters from the inputs
                    required_params = {}
                    if (
                        "parameters" in tool_info
                        and "required" in tool_info["parameters"]
                    ):
                        for param in tool_info["parameters"]["required"]:
                            if param in inputs:
                                required_params[param] = inputs[param]

                    try:
                        tool_instance = tool_attr(**required_params)
                    except Exception:
                        # Last resort: try with no parameters
                        tool_instance = tool_attr()

                # Call the _run method with inputs
                result = tool_instance._run(**inputs)
            except Exception as e:
                logging.error(f"Error executing class-based tool: {str(e)}")
                raise Exception(f"Failed to execute tool: {str(e)}")
        else:
            # Function-based tool: might be a function or a BaseTool instance returned by @tool decorator
            try:
                # Check if it's a BaseTool instance (from @tool decorator)
                if hasattr(tool_attr, "_run"):
                    # It's a BaseTool instance, use _run method
                    result = tool_attr._run(**inputs)
                else:
                    # It's a regular function, call directly
                    result = tool_attr(**inputs)

                # Handle async functions
                if inspect.iscoroutine(result):
                    import asyncio

                    result = asyncio.run(result)
            except Exception as e:
                logging.error(f"Error executing function-based tool: {str(e)}")
                raise Exception(f"Failed to execute tool: {str(e)}")

        # Convert non-serializable objects to strings
        if not isinstance(result, (str, int, float, bool, list, dict, type(None))):
            result = str(result)

        return JSONResponse(content={"status": "success", "result": result})
    except ImportError as e:
        logging.error(f"Error importing tool module: {str(e)}")
        return JSONResponse(
            content={
                "status": "error",
                "message": f"Error importing tool module: {str(e)}",
            },
            status_code=500,
        )
    except Exception as e:
        logging.error(f"Error executing tool {tool_name}: {str(e)}")
        return JSONResponse(
            content={"status": "error", "message": f"Error executing tool: {str(e)}"},
            status_code=500,
        )


@app.post("/api/crews/{crew_id}/initialize")
async def initialize_crew(crew_id: str) -> JSONResponse:
    """Initialize a specific crew structure without running it.

    Args:
        crew_id: The ID of the crew to initialize

    Returns:
        JSONResponse with initialization status
    """
    try:
        # Find the crew path
        crew_path = None
        for crew in discovered_crews:
            if crew.get("id") == crew_id:
                crew_path = crew.get("path")
                break

        if not crew_path:
            raise HTTPException(
                status_code=404, detail=f"Crew with ID {crew_id} not found"
            )

        # Load the crew
        crew_instance, crew_name = load_crew_from_module(Path(crew_path))

        # Get event bus and set up visualization listener
        if hasattr(crew_instance, "get_event_bus"):
            event_bus = crew_instance.get_event_bus()
        else:
            event_bus = crewai_event_bus

        # Ensure listener is setup
        crew_visualization_listener.setup_listeners(event_bus)

        # Extract agents and tasks info
        agents = []
        for agent in crew_instance.agents:
            agent_id = str(agent.id) if hasattr(agent, "id") else f"agent_{len(agents)}"
            agents.append(
                {
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
            )

        # Extract tasks info
        tasks = []
        task_map = {}
        for i, task in enumerate(crew_instance.tasks):
            task_id = str(task.id) if hasattr(task, "id") else f"task_{i}"
            task_map[task_id] = task

            # Try to find an agent for this task
            assigned_agent_id = None
            if hasattr(task, "agent") and task.agent:
                agent_id = str(task.agent.id) if hasattr(task.agent, "id") else None
                if agent_id:
                    assigned_agent_id = agent_id

            tasks.append(
                {
                    "id": task_id,
                    "description": (
                        task.description if hasattr(task, "description") else ""
                    ),
                    "status": "pending",
                    "agent_id": assigned_agent_id,
                }
            )

        # Emit initialization events
        from crewai_playground.events import (
            CrewInitializationRequestedEvent,
            CrewInitializationCompletedEvent,
        )

        event_bus.emit(
            crew_instance,
            CrewInitializationRequestedEvent(
                crew_id=crew_id,
                crew_name=crew_name,
                timestamp=datetime.datetime.utcnow(),
            ),
        )

        # After extracting structure, emit completion event
        event_bus.emit(
            crew_instance,
            CrewInitializationCompletedEvent(
                crew_id=crew_id,
                crew_name=crew_name,
                agents=agents,
                tasks=tasks,
                timestamp=datetime.datetime.utcnow(),
            ),
        )

        return JSONResponse(
            content={
                "status": "success",
                "message": f"Crew {crew_name} initialized",
                "crew_id": crew_id,
                "agent_count": len(agents),
                "task_count": len(tasks),
            },
            status_code=200,
        )

    except Exception as e:
        logging.error(f"Error initializing crew {crew_id}: {str(e)}")
        return JSONResponse(
            content={
                "status": "error",
                "message": f"Error initializing crew: {str(e)}",
            },
            status_code=500,
        )


@app.post("/api/crews/{crew_id}/kickoff")
async def kickoff_crew(crew_id: str, request: KickoffRequest) -> JSONResponse:
    """Run a specific crew directly with optional inputs.

    Args:
        crew_id: The ID of the crew to run
        request: Optional inputs for the crew

    Returns:
        JSONResponse with the crew run results
    """
    try:
        # Find the crew path from the discovered crews
        crew_path = None
        for crew in discovered_crews:
            if crew.get("id") == crew_id:
                crew_path = crew.get("path")
                break

        if not crew_path:
            raise HTTPException(
                status_code=404,
                detail=f"Crew with ID {crew_id} not found",
            )

        # Load the crew
        crew_instance, crew_name = load_crew_from_module(Path(crew_path))

        # Get the crew's event bus and set up the visualization listener
        if hasattr(crew_instance, "get_event_bus"):
            event_bus = crew_instance.get_event_bus()
            crew_visualization_listener.setup_listeners(event_bus)
            logging.info(f"Crew visualization listener set up for crew: {crew_id}")
        else:
            # If the crew doesn't have a get_event_bus method, use the global event bus
            crew_visualization_listener.setup_listeners(crewai_event_bus)
            logging.info(
                f"Using global event bus for crew: {crew_id} since it doesn't have get_event_bus method"
            )

            # Set the crew ID explicitly to ensure consistent tracking
            if hasattr(crew_instance, "id"):
                logging.info(f"Crew ID from instance: {crew_instance.id}")
            else:
                # Set an ID on the crew instance if it doesn't have one
                import uuid

                crew_instance.id = crew_id
                logging.info(f"Set crew ID to: {crew_id} on crew instance")

        # Create a handler for this crew if it doesn't exist
        if crew_id not in chat_handlers:
            chat_handlers[crew_id] = ChatHandler(crew_instance, crew_name)

        handler = chat_handlers[crew_id]

        # Run the crew directly
        inputs = request.inputs or {}

        # Run the crew kickoff in a separate thread to not block the API
        thread = threading.Thread(target=handler.run_crew, args=(inputs,))
        thread.start()

        return JSONResponse(
            content={
                "status": "success",
                "message": f"Crew '{crew_name}' kickoff started.",
                "crew_id": crew_id,
            }
        )
    except HTTPException as e:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        error_message = f"Error running crew: {str(e)}"
        logging.error(error_message, exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)


@app.websocket("/ws/crew-visualization/{crew_id}")
async def websocket_endpoint(websocket: WebSocket, crew_id: str = None):
    """WebSocket endpoint with optional crew_id path parameter."""
    client_id = str(uuid.uuid4())
    logging.info(
        f"New WebSocket connection request for crew visualization, crew_id: {crew_id}, client_id: {client_id}"
    )

    try:
        # Connect the WebSocket client to the event listener
        await crew_visualization_listener.connect(websocket, client_id, crew_id)
        logging.info(f"WebSocket client {client_id} connected successfully")

        # Send confirmation message
        await websocket.send_json(
            {
                "type": "connection_established",
                "client_id": client_id,
                "crew_id": crew_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

        # Keep the connection open and handle messages
        while True:
            # Wait for messages from the client
            try:
                data = await websocket.receive_text()
                logging.debug(f"Received message from client {client_id}: {data}")

                try:
                    message = json.loads(data)
                    msg_type = message.get("type", "")

                    # Handle crew registration message
                    if msg_type == "register_crew":
                        new_crew_id = message.get("crew_id")
                        if new_crew_id:
                            await crew_visualization_listener.register_client_for_crew(
                                client_id, new_crew_id
                            )
                            await websocket.send_json(
                                {"type": "crew_registered", "crew_id": new_crew_id}
                            )

                    # Handle state request message
                    elif msg_type == "request_state":
                        await crew_visualization_listener.send_state_to_client(
                            client_id
                        )

                    # Handle ping message for heartbeat
                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

                except json.JSONDecodeError:
                    logging.error(
                        f"Invalid JSON message from client {client_id}: {data}"
                    )

            except WebSocketDisconnect:
                # Handle disconnection
                logging.info(f"WebSocket client {client_id} disconnected")
                crew_visualization_listener.disconnect(client_id)
                break
    except WebSocketDisconnect:
        logging.info(f"WebSocket client {client_id} disconnected during handshake")
        crew_visualization_listener.disconnect(client_id)
    except Exception as e:
        logging.error(
            f"WebSocket error for client {client_id}: {str(e)}", exc_info=True
        )
        # Try to disconnect if there was an error
        try:
            crew_visualization_listener.disconnect(client_id)
        except Exception as disconnect_error:
            logging.error(
                f"Error disconnecting client {client_id}: {str(disconnect_error)}"
            )
            pass


@app.websocket("/ws/flow/{flow_id}")
async def flow_websocket_endpoint(websocket: WebSocket, flow_id: str):
    """WebSocket endpoint for real-time flow execution visualization."""
    logging.info(f"New WebSocket connection request for flow {flow_id}")
    await websocket.accept()
    logging.info(f"WebSocket connection attempt for flow: {flow_id}")

    try:
        # Check if this is an API flow ID that needs to be mapped to internal flow ID
        from .flow_api import flow_id_mapping

        internal_flow_id = flow_id_mapping.get(flow_id, flow_id)

        # Check if flow execution exists using the API flow ID (since active flows are stored with API flow ID)
        execution = get_active_execution(flow_id)

        # If no active execution is found, wait a short time for it to be created
        # This helps with race conditions where the WebSocket connects before the flow is fully initialized
        if not execution:
            logging.info(
                f"No active execution found for API flow {flow_id}, waiting for initialization..."
            )
            # Wait up to 5 seconds for the flow execution to be created
            for i in range(10):
                await asyncio.sleep(0.5)
                execution = get_active_execution(flow_id)
                if execution:
                    logging.info(
                        f"Flow execution for API flow {flow_id} found after waiting"
                    )
                    break

        # If still no execution found after waiting, send error
        if not execution:
            logging.error(
                f"No active execution found for API flow {flow_id} after waiting"
            )
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"No active execution found for flow {flow_id}. Please try running the flow again.",
                }
            )
            logging.info(f"Closing WebSocket for flow {flow_id} - no execution found")
            await websocket.close()
            return

        # Create a queue for this connection
        queue: asyncio.Queue = asyncio.Queue()

        # Register this connection with the API flow ID (for UI compatibility)
        connection_id = str(uuid.uuid4())
        register_websocket_queue(flow_id, connection_id, queue)
        logging.info(
            f"Registered WebSocket connection {connection_id} for flow {flow_id}"
        )

        try:
            # Send initial state using the API flow ID (where states are now stored)
            initial_state = flow_websocket_listener.get_flow_state(flow_id)
            if initial_state:
                await websocket.send_json(
                    {"type": "flow_state", "payload": initial_state}
                )
                logging.info(f"Initial state sent for flow {flow_id}")

            # Listen for updates from the flow execution
            while True:
                try:
                    # Wait for messages with a timeout
                    message = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await websocket.send_json(message)
                except asyncio.TimeoutError:
                    # Check if the flow execution is still active using API flow ID
                    if not is_execution_active(flow_id):
                        # Send final state before closing using API flow ID
                        final_state = flow_websocket_listener.get_flow_state(flow_id)
                        if final_state:
                            await websocket.send_json(
                                {"type": "flow_state", "payload": final_state}
                            )
                        logging.info(
                            f"Flow execution completed for {flow_id}, closing WebSocket"
                        )
                        break
                    # Otherwise continue waiting
                    continue
        except WebSocketDisconnect:
            logging.info(f"WebSocket client disconnected: {connection_id}")
        except Exception as e:
            logging.error(f"Error in flow WebSocket: {str(e)}")
        finally:
            # Unregister this connection
            unregister_websocket_queue(flow_id, connection_id)
    except Exception as e:
        logging.error(f"Flow WebSocket error: {str(e)}", exc_info=True)
    finally:
        await websocket.close()


# ============================================================================
# EVALUATION API ENDPOINTS
# ============================================================================


@app.get("/api/evaluations")
async def get_evaluations():
    """Get all evaluation runs with their status and summary."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    try:
        runs = []
        for run_id, run_data in evaluation_runs.items():
            runs.append(
                {
                    "id": run_id,
                    "name": run_data["name"],
                    "status": run_data["status"],
                    "progress": run_data["progress"],
                    "startTime": run_data["start_time"],
                    "endTime": run_data.get("end_time"),
                    "agentCount": run_data["agent_count"],
                    "metricCount": run_data["metric_count"],
                    "overallScore": run_data.get("overall_score"),
                    "iterations": run_data["iterations"],
                }
            )

        return {
            "status": "success",
            "data": {
                "runs": runs,
                "summary": {
                    "total": len(runs),
                    "active": len([r for r in runs if r["status"] == "running"]),
                    "completed": len([r for r in runs if r["status"] == "completed"]),
                    "failed": len([r for r in runs if r["status"] == "failed"]),
                },
            },
        }
    except Exception as e:
        logging.error(f"Error fetching evaluations: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching evaluations: {str(e)}"
        )


@app.post("/api/evaluations")
async def create_evaluation(config: EvaluationConfigRequest):
    """Create and start a new evaluation run."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    try:
        # Generate unique evaluation ID
        eval_id = str(uuid.uuid4())

        # Load crews for evaluation
        crews_to_evaluate = []
        agents_to_evaluate = []

        for crew_id in config.crew_ids:
            try:
                # Find the crew info from discovered crews
                crew_info = None
                for discovered_crew in discovered_crews:
                    if discovered_crew.get("id") == crew_id:
                        crew_info = discovered_crew
                        break

                if not crew_info:
                    logging.warning(f"Crew {crew_id} not found in discovered crews")
                    continue

                # Load the crew from its path
                crew_path = crew_info.get("path")
                if crew_path:
                    from pathlib import Path

                    crew_path_obj = Path(crew_path)  # Convert string to Path object
                    logging.info(f"Loading crew from path: {crew_path_obj}")
                    loaded_crew_data = load_crew_from_module(crew_path_obj)
                    if loaded_crew_data and len(loaded_crew_data) > 0:
                        crew_instance = loaded_crew_data[0]  # Get the crew instance
                        crews_to_evaluate.append(crew_instance)
                        logging.info(f"Loaded crew instance: {crew_instance}")
                        # Extract agents from crew
                        if hasattr(crew_instance, "agents"):
                            crew_agents = crew_instance.agents
                            logging.info(
                                f"Found {len(crew_agents)} agents in crew {crew_id}: {[getattr(agent, 'role', 'Unknown') for agent in crew_agents]}"
                            )
                            agents_to_evaluate.extend(crew_agents)
                        else:
                            logging.warning(f"Crew {crew_id} has no 'agents' attribute")
                    else:
                        logging.warning(
                            f"Failed to load crew data from {crew_path_obj}"
                        )

            except Exception as e:
                logging.warning(f"Failed to load crew {crew_id}: {str(e)}")
                continue

        # If no agents found, we cannot run real evaluations
        if not agents_to_evaluate:
            logging.warning(
                "No real agents found from crews - real evaluations require actual CrewAI agents"
            )
            raise HTTPException(
                status_code=400,
                detail="No real agents found in the selected crews. Real CrewAI evaluations require crews with actual agents. Please ensure your crews are properly configured with agents.",
            )

        # Create evaluation run record
        run_data = {
            "id": eval_id,
            "name": config.name,
            "status": "pending",
            "progress": 0.0,
            "start_time": datetime.datetime.now().isoformat(),
            "end_time": None,
            "agent_count": len(agents_to_evaluate),
            "metric_count": (
                len(config.metric_categories) if config.metric_categories else 6
            ),
            "overall_score": None,
            "iterations": config.iterations,
            "config": {
                "crew_ids": config.crew_ids,
                "metric_categories": config.metric_categories,
                "aggregation_strategy": config.aggregation_strategy,
                "test_inputs": config.test_inputs,
            },
            "agents": [
                {
                    "id": str(
                        agent.get("id")
                        if isinstance(agent, dict)
                        else getattr(agent, "id", "unknown")
                    ),
                    "role": (
                        agent.get("role")
                        if isinstance(agent, dict)
                        else getattr(agent, "role", "Unknown Role")
                    ),
                    "goal": (
                        agent.get("goal")
                        if isinstance(agent, dict)
                        else getattr(agent, "goal", "")
                    ),
                    "backstory": (
                        agent.get("backstory")
                        if isinstance(agent, dict)
                        else getattr(agent, "backstory", "")
                    ),
                }
                for agent in agents_to_evaluate
            ],
        }

        evaluation_runs[eval_id] = run_data

        # Start evaluation in background
        asyncio.create_task(run_evaluation_async(eval_id, agents_to_evaluate, config))

        return {
            "status": "success",
            "data": {
                "evaluation_id": eval_id,
                "message": f"Evaluation '{config.name}' started successfully",
            },
        }

    except Exception as e:
        logging.error(f"Error creating evaluation: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating evaluation: {str(e)}"
        )


@app.get("/api/evaluations/metrics")
async def get_available_metrics():
    """Get list of available evaluation metrics."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    try:
        metrics = [
            {
                "id": "goal_alignment",
                "name": "Goal Alignment",
                "description": "Evaluates how well the agent's output aligns with the given goal",
            },
            {
                "id": "semantic_quality",
                "name": "Semantic Quality",
                "description": "Assesses the semantic quality and coherence of the agent's output",
            },
            {
                "id": "reasoning_efficiency",
                "name": "Reasoning Efficiency",
                "description": "Measures the efficiency of the agent's reasoning process",
            },
            {
                "id": "tool_selection",
                "name": "Tool Selection",
                "description": "Evaluates the appropriateness of tool selection and usage",
            },
            {
                "id": "parameter_extraction",
                "name": "Parameter Extraction",
                "description": "Assesses the accuracy of parameter extraction for tool calls",
            },
            {
                "id": "tool_invocation",
                "name": "Tool Invocation",
                "description": "Evaluates the correctness of tool invocation and usage",
            },
        ]

        aggregation_strategies = [
            {
                "id": "simple_average",
                "name": "Simple Average",
                "description": "Equal weight to all tasks",
            },
            {
                "id": "weighted_by_complexity",
                "name": "Weighted by Complexity",
                "description": "Weight by task complexity",
            },
            {
                "id": "best_performance",
                "name": "Best Performance",
                "description": "Use best scores across tasks",
            },
            {
                "id": "worst_performance",
                "name": "Worst Performance",
                "description": "Use worst scores across tasks",
            },
        ]

        return {
            "status": "success",
            "data": {
                "metrics": metrics,
                "aggregation_strategies": aggregation_strategies,
            },
        }
    except Exception as e:
        logging.error(f"Error fetching available metrics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching available metrics: {str(e)}"
        )


@app.get("/api/evaluations/{evaluation_id}")
async def get_evaluation(evaluation_id: str):
    """Get detailed information about a specific evaluation run."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    if evaluation_id not in evaluation_runs:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    try:
        run_data = evaluation_runs[evaluation_id]
        results = evaluation_results.get(evaluation_id, {})

        return {"status": "success", "data": {"run": run_data, "results": results}}
    except Exception as e:
        logging.error(f"Error fetching evaluation {evaluation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching evaluation: {str(e)}"
        )


@app.get("/api/evaluations/{evaluation_id}/results")
async def get_evaluation_results(evaluation_id: str):
    """Get detailed results for a completed evaluation."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    if evaluation_id not in evaluation_runs:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    try:
        run_data = evaluation_runs[evaluation_id]
        if run_data["status"] != "completed":
            return {
                "status": "success",
                "data": {
                    "message": f"Evaluation is {run_data['status']}",
                    "progress": run_data["progress"],
                },
            }

        results = evaluation_results.get(evaluation_id, {})

        return {
            "status": "success",
            "data": {
                "evaluation_id": evaluation_id,
                "results": results,
                "summary": {
                    "overall_score": run_data.get("overall_score"),
                    "agent_count": run_data["agent_count"],
                    "metric_count": run_data["metric_count"],
                    "iterations": run_data["iterations"],
                },
            },
        }
    except Exception as e:
        logging.error(f"Error fetching evaluation results {evaluation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching evaluation results: {str(e)}"
        )


@app.delete("/api/evaluations/{evaluation_id}")
async def delete_evaluation(evaluation_id: str):
    """Delete an evaluation run and its results."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    if evaluation_id not in evaluation_runs:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    try:
        # Stop active evaluation if running
        if evaluation_id in active_evaluations:
            # Cancel the evaluation task if possible
            del active_evaluations[evaluation_id]

        # Remove from storage
        del evaluation_runs[evaluation_id]
        if evaluation_id in evaluation_results:
            del evaluation_results[evaluation_id]

        return {
            "status": "success",
            "data": {"message": "Evaluation deleted successfully"},
        }
    except Exception as e:
        logging.error(f"Error deleting evaluation {evaluation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting evaluation: {str(e)}"
        )


async def run_evaluation_async(
    eval_id: str, agents: List, config: EvaluationConfigRequest
):
    """Run evaluation asynchronously in the background using real CrewAI evaluation."""
    try:
        # Update status to running
        evaluation_runs[eval_id]["status"] = "running"
        evaluation_runs[eval_id]["progress"] = 10.0

        # Ensure we have agents for evaluation
        if not agents:
            raise ValueError(
                f"No agents provided for evaluation {eval_id}. Real agents are required."
            )

        # Create evaluator with proper setup
        try:
            evaluator = create_default_evaluator(agents=agents)
            active_evaluations[eval_id] = evaluator

        except Exception as e:
            logging.error(f"Failed to create evaluator: {str(e)}")
            raise

        # Find crews that contain these agents
        crews_to_evaluate = []
        for crew_id in config.crew_ids:
            crew_info = next(
                (c for c in discovered_crews if c.get("id") == crew_id), None
            )
            if crew_info:
                try:
                    from pathlib import Path

                    crew_path_obj = Path(crew_info.get("path"))
                    loaded_crew_data = load_crew_from_module(crew_path_obj)
                    if loaded_crew_data and len(loaded_crew_data) > 0:
                        crew_instance = loaded_crew_data[0]
                        crews_to_evaluate.append(crew_instance)
                except Exception as e:
                    logging.warning(
                        f"Failed to load crew {crew_id} for evaluation: {str(e)}"
                    )
                    continue

        if not crews_to_evaluate:
            raise ValueError(
                f"No crews could be loaded for evaluation {eval_id}. Real crews are required."
            )

        # Run real evaluation with crews
        agent_results = await _run_real_evaluation(
            evaluator, crews_to_evaluate, config, eval_id, agents
        )

        # Calculate overall score
        if agent_results:
            overall_scores = [
                result["overall_score"]
                for result in agent_results.values()
                if result["overall_score"] is not None
            ]
            overall_score = (
                sum(overall_scores) / len(overall_scores) if overall_scores else None
            )
        else:
            overall_score = None

        # Store results (agent_results is already in the correct format)
        evaluation_results[eval_id] = {
            "agent_results": agent_results,
            "summary": {
                "overall_score": overall_score,
                "total_agents": len(agent_results),
                "aggregation_strategy": config.aggregation_strategy,
            },
        }

        # Update final status
        evaluation_runs[eval_id]["status"] = "completed"
        evaluation_runs[eval_id]["progress"] = 100.0
        evaluation_runs[eval_id]["end_time"] = datetime.datetime.now().isoformat()
        evaluation_runs[eval_id]["overall_score"] = overall_score

        # Clean up
        if eval_id in active_evaluations:
            del active_evaluations[eval_id]

        logging.info(f"Evaluation {eval_id} completed successfully")

    except Exception as e:
        logging.error(f"Error running evaluation {eval_id}: {str(e)}")
        evaluation_runs[eval_id]["status"] = "failed"
        evaluation_runs[eval_id]["progress"] = 0.0
        evaluation_runs[eval_id]["end_time"] = datetime.datetime.now().isoformat()

        # Clean up
        if eval_id in active_evaluations:
            del active_evaluations[eval_id]


async def _run_real_evaluation(
    evaluator,
    crews_to_evaluate: List,
    config: EvaluationConfigRequest,
    eval_id: str,
    agents: List = None,
) -> dict:
    """Run real CrewAI evaluation with actual crew execution."""
    try:
        # Prepare test inputs for evaluation
        test_inputs = config.test_inputs or {
            "query": "Evaluate agent performance on this task"
        }

        # Dictionary to collect all evaluation events across iterations
        all_evaluation_events = {"started": [], "completed": [], "failed": []}

        # Run evaluation for each iteration
        for iteration in range(1, config.iterations + 1):
            logging.info(
                f"Running evaluation iteration {iteration}/{config.iterations} for {eval_id}"
            )

            # Update progress
            progress = 10.0 + (70.0 * iteration / config.iterations)
            evaluation_runs[eval_id]["progress"] = progress

            # Set evaluator iteration
            evaluator.set_iteration(iteration)

            # Run each crew with the test inputs
            for crew in crews_to_evaluate:
                try:
                    # Create a dictionary to collect events for this crew execution
                    iteration_events = {"started": [], "completed": [], "failed": []}

                    # Use scoped handlers to ensure proper event capture
                    with crewai_event_bus.scoped_handlers():
                        # Register event handlers for evaluation events
                        @crewai_event_bus.on(AgentEvaluationStartedEvent)
                        def capture_started(source, event):
                            logging.info(
                                f"Captured evaluation started event: {event.agent_id}"
                            )
                            iteration_events["started"].append(event)
                            all_evaluation_events["started"].append(event)

                        @crewai_event_bus.on(AgentEvaluationCompletedEvent)
                        def capture_completed(source, event):
                            logging.info(
                                f"Captured evaluation completed event: {event.agent_id}"
                            )
                            iteration_events["completed"].append(event)
                            all_evaluation_events["completed"].append(event)

                        @crewai_event_bus.on(AgentEvaluationFailedEvent)
                        def capture_failed(source, event):
                            logging.error(
                                f"Captured evaluation failed event: {event.agent_id} - {event.error}"
                            )
                            iteration_events["failed"].append(event)
                            all_evaluation_events["failed"].append(event)

                        # Execute the crew with test inputs and properly await it
                        logging.info(f"Executing crew for iteration {iteration}")
                        await crew.kickoff_async(inputs=test_inputs)

                        results = evaluator.get_evaluation_results()
                        print("Evaluation results", results)

                        # Log event capture summary
                        logging.info(
                            f"Captured {len(iteration_events['started'])} started, "
                            f"{len(iteration_events['completed'])} completed, and "
                            f"{len(iteration_events['failed'])} failed events for iteration {iteration}"
                        )

                except Exception as e:
                    logging.error(f"Error: {str(e)}")
                    continue

            # Small delay between iterations
            await asyncio.sleep(1)

        # Log event capture summary for all iterations
        logging.info(
            f"Total captured events for {eval_id}: "
            f"{len(all_evaluation_events['started'])} started, "
            f"{len(all_evaluation_events['completed'])} completed, and "
            f"{len(all_evaluation_events['failed'])} failed events"
        )

        # Get evaluation results from the evaluator
        logging.info(f"Collecting evaluation results for {eval_id}")
        evaluation_results = evaluator.get_evaluation_results()
        print(f"Raw evaluation results for {eval_id}: {evaluation_results}")

        # Convert CrewAI evaluation results to our format
        agent_results = {}

        if not evaluation_results:
            # Enhanced error message with event counts to help diagnose issues
            error_msg = f"No evaluation results returned from evaluator for {eval_id}."
            logging.error(error_msg)

            # If we have failed events, include their errors in the exception
            if all_evaluation_events["failed"]:
                error_details = [
                    f"{e.agent_id}: {e.error}" for e in all_evaluation_events["failed"]
                ]
                error_msg += f" Failures: {'; '.join(error_details)}"

            raise RuntimeError(error_msg)

        # Process evaluation results by agent role
        for agent_role, results_list in evaluation_results.items():
            if not results_list:
                logging.warning(
                    f"No results for agent {agent_role} in evaluation {eval_id}"
                )
                continue

            # Aggregate results across all iterations for this agent
            total_scores = {}
            total_feedback = []
            task_count = len(results_list)
            agent_id = None

            # Process each evaluation result for this agent
            for result in results_list:
                # Store agent_id for consistent reference
                if agent_id is None and hasattr(result, "agent_id"):
                    agent_id = str(result.agent_id)

                # Extract metrics from AgentEvaluationResult
                for metric_category, evaluation_score in result.metrics.items():
                    # Handle different metric category formats
                    metric_name = (
                        metric_category.value
                        if hasattr(metric_category, "value")
                        else str(metric_category)
                    )

                    if metric_name not in total_scores:
                        total_scores[metric_name] = []

                    # Add score if available
                    if evaluation_score.score is not None:
                        total_scores[metric_name].append(evaluation_score.score)

                    # Add feedback if available
                    if evaluation_score.feedback:
                        total_feedback.append(
                            f"{metric_name}: {evaluation_score.feedback}"
                        )

            # Calculate average scores and format metrics
            metrics = {}
            overall_scores = []

            for metric_name, scores in total_scores.items():
                if scores:
                    avg_score = sum(scores) / len(scores)
                    metrics[metric_name] = {
                        "score": round(avg_score, 1),
                        "feedback": f"Average score across {len(scores)} evaluations",
                        "color": _get_score_color(
                            avg_score
                        ),  # Add color coding based on score
                    }
                    overall_scores.append(avg_score)

            # Calculate overall score from metrics
            if overall_scores:
                overall_score = round(sum(overall_scores) / len(overall_scores), 1)
                overall_color = _get_score_color(overall_score)
            else:
                # No scores captured - this indicates an evaluation system issue
                logging.error(
                    f"No metric scores captured for agent {agent_role} in evaluation {eval_id}"
                )
                overall_score = None
                overall_color = None
                metrics = {}

            # Create the agent result entry
            agent_results[agent_role] = {
                "agent_id": agent_id or f"agent_{agent_role}",
                "agent_role": agent_role,
                "overall_score": overall_score,
                "overall_color": overall_color,
                "metrics": metrics,
                "task_count": task_count,
                "feedback": (
                    total_feedback
                    if total_feedback
                    else ["No detailed feedback available"]
                ),
            }

        # Calculate summary statistics
        total_agents = len(agent_results)
        all_agent_scores = [
            ar["overall_score"]
            for ar in agent_results.values()
            if ar["overall_score"] is not None
        ]

        # Add summary information to the results
        result = {
            "agent_results": agent_results,
            "summary": {
                "overall_score": (
                    round(sum(all_agent_scores) / len(all_agent_scores), 1)
                    if all_agent_scores
                    else None
                ),
                "total_agents": total_agents,
                "aggregation_strategy": config.aggregation_strategy,
            },
        }

        logging.info(
            f"Real evaluation completed for {eval_id} with {len(agent_results)} agent results"
        )
        return result

    except Exception as e:
        logging.error(f"Error in real evaluation for {eval_id}: {str(e)}")
        # Re-raise the error since we don't support mock fallbacks
        raise RuntimeError(f"Real evaluation failed for {eval_id}: {str(e)}") from e


def _get_score_color(score):
    """Return a color based on the evaluation score."""
    if score is None:
        return None
    elif score >= 8.0:
        return "green"
    elif score >= 5.0:
        return "yellow"
    else:
        return "red"


@app.get("/{full_path:path}")
async def serve_ui(full_path: str):
    """Serve the React application and handle client-side routing."""
    # Check if the path points to an existing file in the build directory
    requested_file = ui_dir / full_path

    if requested_file.exists() and requested_file.is_file():
        return FileResponse(requested_file)

    # If ui/build/client/index.html exists, serve it for client-side routing
    if ui_dir.exists() and (ui_dir / "index.html").exists():
        return FileResponse(ui_dir / "index.html")


def show_loading(stop_event, message):
    """Display animated loading dots while processing."""
    counter = 0
    while not stop_event.is_set():
        dots = "." * (counter % 4)
        click.echo(f"\r{message}{dots.ljust(3)}", nl=False)
        counter += 1
        threading.Event().wait(0.5)
    click.echo()  # Final newline


def find_available_port(start_port: int = 8000, max_attempts: int = 100) -> int:
    """Find the next available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))
                return port
        except OSError:
            continue
    raise RuntimeError(
        f"Could not find an available port after {max_attempts} attempts"
    )


def main():
    """Main entry point for the CLI."""
    global chat_handler, discovered_crews

    click.echo("CrewAI Playground - Starting up...")

    try:
        # Try to discover all crews in the current directory
        click.echo("Discovering crews in current directory...")

        # Show loading indicator for crew loading
        stop_loading = threading.Event()
        loading_thread = threading.Thread(
            target=show_loading, args=(stop_loading, "Searching for crew files")
        )
        loading_thread.start()

        try:
            # Discover all available crews
            crews_info = discover_available_crews()

            # Add unique IDs to each crew
            for i, crew in enumerate(crews_info):
                crew["id"] = f"crew_{i}" if not crew.get("id") else crew["id"]

            discovered_crews = crews_info

            stop_loading.set()
            loading_thread.join()

            if crews_info:
                click.echo(f"Found {len(crews_info)} crews:")
                for i, crew in enumerate(crews_info):
                    click.echo(f"  {i+1}. {crew['name']} - {crew['directory']}")

                # Initialize the first crew
                try:
                    crew_path = Path(crews_info[0]["path"])
                    crew, crew_name = load_crew_from_module(crew_path)
                    chat_handler = ChatHandler(crew, crew_name)
                    chat_handlers[crews_info[0]["id"]] = chat_handler
                    click.echo(f"Initialized {crew_name} as the default crew")
                except Exception as e:
                    click.echo(f"Error initializing first crew: {str(e)}", err=True)
            else:
                click.echo("No crews found. Trying fallback method...")
                try:
                    # Fallback to the original method
                    crew, crew_name = load_crew()
                    chat_handler = ChatHandler(crew, crew_name)
                    click.echo(f"Successfully loaded crew: {crew_name}")

                    # Add this to discovered crews
                    discovered_crews = [
                        {
                            "id": "default_crew",
                            "name": crew_name,
                            "path": str(Path(os.getcwd()) / "crew.py"),
                            "directory": ".",
                        }
                    ]
                except Exception as e:
                    click.echo(f"Error loading crew: {str(e)}", err=True)

                    # Add helpful debugging information
                    click.echo("\nFor debugging help:")
                    click.echo(
                        "1. Make sure your crew.py file contains a Crew instance or a function that returns one"
                    )
                    click.echo(
                        "2. If using a function, name it 'crew', 'get_crew', 'create_crew', or similar"
                    )
                    click.echo(
                        "3. Check that your CrewAI imports are correct for your installed version"
                    )
                    click.echo(
                        "4. Run your crew file directly with 'python crew.py' to test it"
                    )
                    sys.exit(1)
        except Exception as e:
            stop_loading.set()
            loading_thread.join()
            click.echo(f"Error discovering crews: {str(e)}", err=True)
            sys.exit(1)

        # Start the FastAPI server with uvicorn
        host = "0.0.0.0"  # Listen on all interfaces
        default_port = 8000

        try:
            port = find_available_port(default_port)
            if port != default_port:
                click.echo(
                    click.style(
                        f"Port {default_port} is in use, using port {port} instead",
                        fg="yellow",
                    )
                )
        except RuntimeError as e:
            click.echo(f"Error finding available port: {str(e)}", err=True)
            sys.exit(1)

        click.echo(
            click.style(f"Server running! Access the chat UI at: ", fg="green")
            + click.style(f"http://localhost:{port}", fg="bright_green", bold=True)
        )
        click.echo(click.style("Press Ctrl+C to stop the server", fg="yellow"))

        # Run the FastAPI app with uvicorn
        uvicorn.run(app, host=host, port=port, log_level="error")

    except KeyboardInterrupt:
        click.echo("\nServer stopped")
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
