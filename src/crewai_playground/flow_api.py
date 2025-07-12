"""
Flow API for CrewAI Playground

This module provides API endpoints for managing CrewAI flows.
"""

import os
from typing import Dict, List, Any, Optional
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .flow_loader import (
    FlowInput,
    FlowInfo,
    load_flow,
    discover_flows,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/flows", tags=["flows"])

# In-memory storage for flows and traces
flows_cache: Dict[str, FlowInfo] = {}
# Global state for active flows and traces
active_flows: Dict[str, Dict[str, Any]] = {}
flow_traces: Dict[str, List[Dict[str, Any]]] = {}
flow_states: Dict[str, Dict[str, Any]] = {}
# Mapping between API flow IDs and internal CrewAI flow IDs
flow_id_mapping: Dict[str, str] = {}  # api_flow_id -> internal_flow_id
reverse_flow_id_mapping: Dict[str, str] = {}  # internal_flow_id -> api_flow_id

# Import after defining the above to avoid circular imports
from .websocket_utils import (
    broadcast_flow_update,
    register_websocket_queue,
    unregister_websocket_queue,
    flow_websocket_queues,
)
from .flow_event_listener import flow_websocket_listener


class FlowExecuteRequest(BaseModel):
    """Request model for flow execution"""

    inputs: Dict[str, Any]


class FlowResponse(BaseModel):
    """Response model for flow information"""

    id: str
    name: str
    description: str
    required_inputs: List[FlowInput] = []


@router.on_event("startup")
async def startup_event():
    """Load flows on startup"""
    refresh_flows()


def refresh_flows():
    """Refresh the flows cache"""
    global flows_cache

    # Get the flows directory from environment or use current directory
    flows_dir = os.environ.get("CREWAI_FLOWS_DIR", os.getcwd())

    # Discover flows
    flows = discover_flows(flows_dir)

    # Update cache
    flows_cache = {flow.id: flow for flow in flows}

    logger.info(f"Loaded {len(flows_cache)} flows")


# Load flows immediately on module import to ensure cache is populated even if
# the router-level startup event is not executed (which can happen when
# FastAPI mounts routers without triggering individual router events).
refresh_flows()


@router.get("/")
@router.get("")
async def get_flows() -> Dict[str, Any]:
    """
    Get all available flows

    Returns:
        Dict with list of flows
    """
    flow_list = [
        {"id": flow.id, "name": flow.name, "description": flow.description}
        for flow in flows_cache.values()
    ]

    return {"status": "success", "flows": flow_list}


@router.get("/{flow_id}/initialize")
async def initialize_flow(flow_id: str) -> Dict[str, Any]:
    """
    Initialize a flow and get its required inputs

    Args:
        flow_id: ID of the flow to initialize

    Returns:
        Dict with flow initialization data
    """
    if flow_id not in flows_cache:
        raise HTTPException(status_code=404, detail="Flow not found")

    flow_info = flows_cache[flow_id]

    return {
        "status": "success",
        "required_inputs": [
            {"name": input.name, "description": input.description}
            for input in flow_info.required_inputs
        ],
    }


def _execute_flow_sync(flow_id: str, inputs: Dict[str, Any]):
    """
    Execute a flow synchronously in a thread

    Args:
        flow_id: ID of the flow to execute
        inputs: Input parameters for the flow
    """
    logger.info(f"Starting threaded execution of flow: {flow_id}")
    
    # Create an event loop for this thread if needed
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Run the async function in this thread's event loop
    try:
        return loop.run_until_complete(_execute_flow_async(flow_id, inputs))
    except Exception as e:
        logger.error(f"Error in threaded flow execution: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def _execute_flow_async(flow_id: str, inputs: Dict[str, Any]):
    """
    Execute a flow asynchronously

    Args:
        flow_id: ID of the flow to execute
        inputs: Input parameters for the flow
    """
    logger.info(f"Starting async execution of flow: {flow_id}")

    try:
        # Create a test file to verify this function is being called
        import os

        test_file_path = f"/tmp/flow_execution_test_{flow_id}.txt"
        with open(test_file_path, "w") as f:
            f.write(f"Flow execution started at {asyncio.get_event_loop().time()}\n")

        # Get flow info from cache or discover it
        if flow_id in flows_cache:
            flow_info = flows_cache[flow_id]
        else:
            # Discover available flows
            available_flows = discover_flows()
            flows_cache.update({flow.id: flow for flow in available_flows})
            flow_info = flows_cache.get(flow_id)

        if not flow_info:
            return {"status": "error", "message": f"Flow {flow_id} not found"}

        # Load flow using the FlowInfo object
        flow = load_flow(flow_info, inputs)
        if not flow:
            logger.error(f"Flow loading failed for {flow_id}")
            return {"status": "error", "message": f"Flow {flow_id} not found"}

        logger.info(f"Flow loaded successfully: {flow_id}")

        # Initialize flow state through the event listener
        # The event listener will handle this when it receives the flow_started event
        # but we'll keep a reference in active_flows for tracking active executions
        active_flows[flow_id] = {
            "id": flow_id,
            "status": "running",
            "timestamp": asyncio.get_event_loop().time(),
        }
        logger.info(f"Registered active flow: {flow_id}")

        # Initialize trace for this execution
        current_time = asyncio.get_event_loop().time()
        trace = {
            "id": str(uuid.uuid4()),
            "flow_id": flow_id,
            "start_time": current_time,
            "end_time": None,
            "status": "running",
            "inputs": inputs,
            "output": None,
            "error": None,
            "events": [
                {
                    "type": "status_change",
                    "timestamp": current_time,
                    "data": {"status": "running"},
                }
            ],
        }

        # Add trace to flow_traces
        if flow_id not in flow_traces:
            flow_traces[flow_id] = []
        flow_traces[flow_id].append(trace)

        # The event listener will handle adding steps to the flow state
        # when it receives method execution events

        # The event listener will handle sending the initial flow state via WebSocket
        # when it receives the flow_started event

        # Register the flow WebSocket event listener with the global CrewAI event bus
        # This will capture all flow events and broadcast them via WebSocket
        logger.info(f"Registering flow WebSocket event listener for flow: {flow_id}")

        try:
            from crewai.utilities.events.crewai_event_bus import crewai_event_bus

            # Register our listener with the global event bus
            # The listener will filter events by flow_id
            logger.info(f"Setting up event listeners for flow: {flow_id}")
            flow_websocket_listener.setup_listeners(crewai_event_bus)
            logger.info(f"Successfully registered event listener for flow: {flow_id}")

            # Emit flow started event using the global event bus
            from crewai.utilities.events import FlowStartedEvent

            logger.info(f"Creating FlowStartedEvent for {flow.__class__.__name__}")
            flow_started_event = FlowStartedEvent(
                flow_name=flow.__class__.__name__, inputs=inputs
            )
            logger.info(f"Emitting FlowStartedEvent via crewai_event_bus")
            crewai_event_bus.emit(flow, flow_started_event)
            logger.info(f"Successfully emitted FlowStartedEvent for flow: {flow_id}")

        except Exception as e:
            logger.error(f"Failed to set up flow event handling: {e}")
            # Continue without events - flow will still execute

        # Wrap flow execution to emit method execution events using global event bus
        async def emit_method_events(method_name, method_func, *args, **kwargs):
            """Wrapper to emit method execution events."""
            try:
                from crewai.utilities.events.crewai_event_bus import crewai_event_bus
                from crewai.utilities.events import MethodExecutionStartedEvent

                # Emit method started event
                start_event = MethodExecutionStartedEvent(
                    flow_name=flow.__class__.__name__,
                    method_name=method_name,
                    state=getattr(flow, "state", {}),
                )
                crewai_event_bus.emit(flow, start_event)
                logger.debug(f"Emitted MethodExecutionStartedEvent for {method_name}")
            except Exception as e:
                logger.error(f"Failed to emit MethodExecutionStartedEvent: {e}")

            try:
                # Execute the method
                if asyncio.iscoroutinefunction(method_func):
                    result = await method_func(*args, **kwargs)
                else:
                    result = method_func(*args, **kwargs)

                # Emit method finished event
                try:
                    from crewai.utilities.events import MethodExecutionFinishedEvent

                    finish_event = MethodExecutionFinishedEvent(
                        flow_name=flow.__class__.__name__,
                        method_name=method_name,
                        result=result,
                        state=getattr(flow, "state", {}),
                    )
                    crewai_event_bus.emit(flow, finish_event)
                    logger.debug(
                        f"Emitted MethodExecutionFinishedEvent for {method_name}"
                    )
                except Exception as e:
                    logger.error(f"Failed to emit MethodExecutionFinishedEvent: {e}")

                return result
            except Exception as e:
                # Emit method failed event
                try:
                    from crewai.utilities.events import MethodExecutionFailedEvent

                    failed_event = MethodExecutionFailedEvent(
                        flow_name=flow.__class__.__name__,
                        method_name=method_name,
                        error=e,
                        state=getattr(flow, "state", {}),
                    )
                    crewai_event_bus.emit(flow, failed_event)
                    logger.debug(
                        f"Emitted MethodExecutionFailedEvent for {method_name}"
                    )
                except Exception as emit_e:
                    logger.error(f"Failed to emit MethodExecutionFailedEvent: {emit_e}")
                raise

        # Execute flow with event emission
        logger.info(f"Checking flow execution methods for {flow.__class__.__name__}")
        logger.info(f"Has run_async: {hasattr(flow, 'run_async')}")
        logger.info(f"Has kickoff_async: {hasattr(flow, 'kickoff_async')}")
        logger.info(f"Has run: {hasattr(flow, 'run')}")
        logger.info(f"Has kickoff: {hasattr(flow, 'kickoff')}")

        if hasattr(flow, "run_async"):
            logger.info(f"Executing flow via run_async method")

            # Capture internal flow ID after execution starts
            result = await emit_method_events("run_async", flow.run_async)

            # Check if flow has an internal ID and create mapping
            internal_flow_id = getattr(flow, "id", None)
            if internal_flow_id and internal_flow_id != flow_id:
                logger.info(
                    f"Creating flow ID mapping: API {flow_id} -> Internal {internal_flow_id}"
                )
                flow_id_mapping[flow_id] = internal_flow_id
                reverse_flow_id_mapping[internal_flow_id] = flow_id
        elif hasattr(flow, "kickoff_async"):
            logger.info(f"Executing flow via kickoff_async method")
            result = await emit_method_events("kickoff_async", flow.kickoff_async)

            # Check if flow has an internal ID and create mapping
            internal_flow_id = getattr(flow, "id", None)
            if internal_flow_id and internal_flow_id != flow_id:
                logger.info(
                    f"Creating flow ID mapping: API {flow_id} -> Internal {internal_flow_id}"
                )
                flow_id_mapping[flow_id] = internal_flow_id
                reverse_flow_id_mapping[internal_flow_id] = flow_id
        elif hasattr(flow, "run"):
            logger.info(f"Executing flow via run method")
            result = await emit_method_events("run", flow.run)

            # Check if flow has an internal ID and create mapping
            internal_flow_id = getattr(flow, "id", None)
            if internal_flow_id and internal_flow_id != flow_id:
                logger.info(
                    f"Creating flow ID mapping: API {flow_id} -> Internal {internal_flow_id}"
                )
                flow_id_mapping[flow_id] = internal_flow_id
                reverse_flow_id_mapping[internal_flow_id] = flow_id
        elif hasattr(flow, "kickoff"):
            logger.info(f"Executing flow via kickoff method")
            result = await emit_method_events("kickoff", flow.kickoff)

            # Check if flow has an internal ID and create mapping
            internal_flow_id = getattr(flow, "id", None)
            if internal_flow_id and internal_flow_id != flow_id:
                logger.info(
                    f"Creating flow ID mapping: API {flow_id} -> Internal {internal_flow_id}"
                )
                flow_id_mapping[flow_id] = internal_flow_id
                reverse_flow_id_mapping[internal_flow_id] = flow_id
        else:
            raise AttributeError(
                f"'{flow.__class__.__name__}' object has no run, run_async, kickoff_async, or kickoff method"
            )

        logger.info(
            f"Flow execution completed: {flow_id} with result type: {type(result)}"
        )

        # Emit flow finished event using global event bus
        try:
            from crewai.utilities.events.crewai_event_bus import crewai_event_bus
            from crewai.utilities.events import FlowFinishedEvent

            logger.info(
                f"Emitting flow finished event for flow: {flow_id} ({flow.__class__.__name__})"
            )
            flow_finished_event = FlowFinishedEvent(
                flow_name=flow.__class__.__name__, result=result
            )
            logger.info(f"Emitting FlowFinishedEvent via crewai_event_bus")
            crewai_event_bus.emit(flow, flow_finished_event)
            logger.info(f"Successfully emitted FlowFinishedEvent for flow: {flow_id}")
        except Exception as e:
            logger.error(f"Failed to emit FlowFinishedEvent: {e}")

        # Update our reference in active_flows
        if flow_id in active_flows:
            active_flows[flow_id]["status"] = "completed"

        # Update trace with results
        if flow_id in flow_traces and flow_traces[flow_id]:
            trace = flow_traces[flow_id][-1]
            trace["status"] = "completed"
            trace["end_time"] = asyncio.get_event_loop().time()
            trace["output"] = result
            trace["events"].append(
                {
                    "type": "status_change",
                    "timestamp": trace["end_time"],
                    "data": {"status": "completed"},
                }
            )

        # Clean up
        if flow_id in active_flows:
            del active_flows[flow_id]

        return result

    except Exception as e:
        logger.error(
            f"Flow execution error in {flow_id}: {str(e)} ({type(e).__name__})"
        )
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.error(f"Error executing flow {flow_id}: {str(e)}", exc_info=True)

        # The event listener will handle updating the flow state with error
        # when it receives the method_execution_failed event
        # We just need to update our reference in active_flows
        if flow_id in active_flows:
            active_flows[flow_id]["status"] = "failed"

        # Update trace with error
        if flow_id in flow_traces and flow_traces[flow_id]:
            trace = flow_traces[flow_id][-1]
            trace["status"] = "failed"
            trace["end_time"] = asyncio.get_event_loop().time()
            trace["error"] = str(e)
            trace["events"].append(
                {
                    "type": "error",
                    "timestamp": trace["end_time"],
                    "data": {"error": str(e)},
                }
            )

        # Clean up
        if flow_id in active_flows:
            del active_flows[flow_id]

        raise


@router.post("/{flow_id}/execute")
async def execute_flow(
    flow_id: str, request: FlowExecuteRequest
) -> Dict[str, Any]:
    """
    Execute a flow with the provided inputs

    Args:
        flow_id: ID of the flow to execute
        request: Flow execution request with inputs

    Returns:
        Dict with execution status
    """
    logger.info(f"Executing flow: {flow_id} with inputs: {request.inputs}")

    if flow_id not in flows_cache:
        raise HTTPException(status_code=404, detail="Flow not found")

    try:
        flow_info = flows_cache[flow_id]

        # Create a trace entry immediately to ensure it exists before WebSocket connection
        trace_id = f"trace_{len(flow_traces.get(flow_id, []))}"
        trace = {
            "id": trace_id,
            "flow_id": flow_id,
            "flow_name": flow_info.name,
            "status": "initializing",
            "start_time": asyncio.get_event_loop().time(),
            "nodes": {},
            "edges": [],
            "events": [],
        }

        # Store trace
        if flow_id not in flow_traces:
            flow_traces[flow_id] = []
        flow_traces[flow_id].append(trace)

        # Initialize a simple reference in active_flows for tracking
        # The event listener will handle the full flow state management
        active_flows[flow_id] = {
            "id": flow_id,
            "status": "initializing",
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Start the flow execution in a separate thread to not block the API
        import threading
        thread = threading.Thread(target=_execute_flow_sync, args=(flow_id, request.inputs))
        thread.daemon = True
        thread.start()

        return {
            "status": "success",
            "detail": f"Flow {flow_id} execution started",
            "flow_id": flow_id,
            "trace_id": trace_id,
        }

    except Exception as e:
        logger.error(f"Error starting flow execution: {str(e)}", exc_info=True)
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Error starting flow execution: {str(e)}"
        )


@router.get("/{flow_id}/traces")
async def get_flow_traces(flow_id: str):
    """
    Get execution traces for a flow

    Args:
        flow_id: ID of the flow

    Returns:
        List of trace objects
    """
    if flow_id not in flow_traces:
        return {"status": "success", "traces": []}

    return {"status": "success", "traces": flow_traces[flow_id]}


@router.get("/{flow_id}/structure")
async def get_flow_structure(flow_id: str):
    """
    Get the structure of a flow for visualization

    Args:
        flow_id: ID of the flow

    Returns:
        Dict with flow structure information
    """
    if flow_id not in flows_cache:
        raise HTTPException(status_code=404, detail="Flow not found")

    flow_info = flows_cache[flow_id]

    try:
        # Build nodes & edges using pre-extracted metadata from FlowInfo
        methods = []
        dependencies = {}

        for m in flow_info.methods:
            methods.append(
                {
                    "id": m.name,
                    "name": m.name.replace("_", " ").title(),
                    "description": m.description,
                    "is_step": m.is_start
                    or m.is_listener
                    or m.is_router,  # treat all as steps
                    "dependencies": m.listens_to,
                    "is_start": m.is_start,
                    "is_listener": m.is_listener,
                }
            )
            dependencies[m.name] = m.listens_to

        # Fallback: if FlowInfo.methods empty (e.g. older cache) use old reflection
        if not methods:
            # Use old reflection to get methods
            methods = []
            flow_class = getattr(flow_info, "flow_class", None)
            if flow_class:
                for name, attr in inspect.getmembers(
                    flow_class, predicate=inspect.isfunction
                ):
                    if name.startswith("_"):
                        continue
                    methods.append(
                        {
                            "id": name,
                            "name": name.replace("_", " ").title(),
                            "description": attr.__doc__.strip() if attr.__doc__ else "",
                            "is_step": True,
                            "dependencies": getattr(attr, "dependencies", []),
                            "is_start": getattr(attr, "is_start", False),
                            "is_listener": getattr(attr, "is_listener", False),
                        }
                    )

        # Return the flow structure
        return {
            "status": "success",
            "flow": {
                "id": flow_info.id,
                "name": flow_info.name,
                "description": flow_info.description,
                "methods": methods,
            },
        }

    except Exception as e:
        logger.error(f"Error getting flow structure: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting flow structure: {str(e)}"
        )


# WebSocket management functions moved to websocket_utils.py


# WebSocket broadcasting functions moved to websocket_utils.py


def get_active_execution(flow_id: str):
    """
    Get the active flow execution for a flow ID

    Args:
        flow_id: ID of the flow

    Returns:
        Active flow execution or None if not found
    """
    result = active_flows.get(flow_id)
    return result


def is_execution_active(flow_id: str) -> bool:
    """
    Check if a flow execution is active

    Args:
        flow_id: ID of the flow

    Returns:
        True if the flow execution is active, False otherwise
    """
    return flow_id in active_flows


def get_flow_state(flow_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the current state of a flow execution

    Args:
        flow_id: ID of the flow

    Returns:
        Current state of the flow execution or None if not found
    """
    # Use the flow_websocket_listener's flow state cache
    from .flow_event_listener import flow_websocket_listener

    return flow_websocket_listener.get_flow_state(flow_id)
