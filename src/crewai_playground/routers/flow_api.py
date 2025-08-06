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

from crewai_playground.loaders.flow_loader import (
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
# Entity service for ID management (replaces local mappings)
from crewai_playground.services.entities import entity_service


def register_flow_entity(flow, flow_id: str):
    """Register a flow entity with the entity service."""
    internal_flow_id = getattr(flow, "id", None)
    python_object_id = str(id(flow))
    flow_name = getattr(
        flow, "name", getattr(flow.__class__, "__name__", "Unknown Flow")
    )

    # Register with entity service
    entity_service.register_entity(
        primary_id=flow_id,
        internal_id=internal_flow_id if internal_flow_id != flow_id else None,
        entity_type="flow",
        name=flow_name,
        aliases=[python_object_id] if python_object_id != flow_id else None,
    )

    logger.info(
        f"Registered flow entity: API {flow_id} -> Internal {internal_flow_id}, Object ID {python_object_id}"
    )


# Import after defining the above to avoid circular imports
from crewai_playground.events.websocket_utils import (
    broadcast_flow_update,
    register_websocket_queue,
    unregister_websocket_queue,
    flow_websocket_queues,
)
from crewai_playground.events.event_listener import (
    event_listener as flow_websocket_listener,
)


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


async def _execute_flow_with_real_time_events(flow, flow_id: str, inputs: Dict[str, Any]):
    """
    Execute a flow with real-time event emission by intercepting method calls.
    This enables progressive visualization updates like crew execution.
    
    Args:
        flow: The flow instance to execute
        flow_id: ID of the flow
        inputs: Input parameters for the flow
        
    Returns:
        Flow execution result
    """
    import inspect
    import asyncio
    from crewai.flow.flow import FlowStartedEvent, FlowFinishedEvent
    from crewai.flow.flow import MethodExecutionStartedEvent, MethodExecutionFinishedEvent, MethodExecutionFailedEvent
    from crewai.utilities.events import crewai_event_bus
    
    logger.info(f"🔄 Starting real-time flow execution for: {flow_id}")
    
    # Emit flow started event
    flow_started_event = FlowStartedEvent(
        flow_name=flow.__class__.__name__,
        flow_id=flow_id,
        inputs=inputs
    )
    crewai_event_bus.emit(flow, flow_started_event)
    logger.info(f"📡 Emitted FlowStartedEvent for: {flow_id}")
    
    try:
        # Get all methods that should be tracked for real-time updates
        flow_methods = _get_flow_execution_methods(flow)
        logger.info(f"🔍 Found {len(flow_methods)} methods to track: {[m.__name__ for m in flow_methods]}")
        
        # Wrap each method with event emission
        original_methods = {}
        for method in flow_methods:
            method_name = method.__name__
            original_methods[method_name] = getattr(flow, method_name)
            
            # Create wrapped method that emits events
            wrapped_method = _create_event_emitting_wrapper(
                original_methods[method_name], 
                method_name, 
                flow, 
                flow_id
            )
            setattr(flow, method_name, wrapped_method)
            logger.info(f"🎯 Wrapped method: {method_name}")
        
        # Execute the flow using the appropriate method
        result = None
        if hasattr(flow, 'run_async'):
            logger.info(f"✅ Using flow.run_async() for real-time execution")
            result = await flow.run_async()
        elif hasattr(flow, 'kickoff_async'):
            logger.info(f"✅ Using flow.kickoff_async() for real-time execution")
            result = await flow.kickoff_async(inputs=inputs)
        elif hasattr(flow, 'run'):
            logger.info(f"⚠️ Using flow.run() in thread pool")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: flow.run())
        elif hasattr(flow, 'kickoff'):
            logger.info(f"⚠️ Using flow.kickoff() in thread pool")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: flow.kickoff(inputs=inputs))
        else:
            raise AttributeError(
                f"'{flow.__class__.__name__}' object has no run, run_async, kickoff_async, or kickoff method"
            )
        
        # Restore original methods
        for method_name, original_method in original_methods.items():
            setattr(flow, method_name, original_method)
            
        logger.info(f"✅ Flow execution completed successfully")
        
        # Emit flow finished event
        flow_finished_event = FlowFinishedEvent(
            flow_name=flow.__class__.__name__,
            flow_id=flow_id,
            result=result
        )
        crewai_event_bus.emit(flow, flow_finished_event)
        logger.info(f"📡 Emitted FlowFinishedEvent for: {flow_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Flow execution failed: {e}")
        
        # Emit flow finished event with error
        flow_finished_event = FlowFinishedEvent(
            flow_name=flow.__class__.__name__,
            flow_id=flow_id,
            error=str(e)
        )
        crewai_event_bus.emit(flow, flow_finished_event)
        
        raise


def _get_flow_execution_methods(flow):
    """
    Get all methods in a flow that should be tracked for real-time updates.
    This includes methods decorated with @start, @listen, @router, etc.
    """
    import inspect
    
    methods = []
    for name, method in inspect.getmembers(flow, predicate=inspect.ismethod):
        # Skip private methods and built-in methods
        if name.startswith('_') or name in ['run', 'kickoff', 'run_async', 'kickoff_async']:
            continue
            
        # Check if method has flow decorators or is likely a flow step
        if _is_flow_step_method(method):
            methods.append(method)
            
    return methods


def _is_flow_step_method(method):
    """
    Check if a method is likely a flow step that should be tracked.
    """
    # Check for common flow decorators
    if hasattr(method, '__wrapped__') or hasattr(method, '__annotations__'):
        method_str = str(method)
        flow_decorators = ['start', 'listen', 'router', 'persist', 'step']
        if any(decorator in method_str for decorator in flow_decorators):
            return True
    
    # Check method name patterns common in flows
    method_name = method.__name__
    flow_patterns = ['generate', 'process', 'create', 'save', 'analyze', 'execute', 'run']
    if any(pattern in method_name.lower() for pattern in flow_patterns):
        return True
        
    return False


def _create_event_emitting_wrapper(original_method, method_name, flow, flow_id):
    """
    Create a wrapper around a flow method that emits events before and after execution.
    """
    import functools
    import asyncio
    from crewai.flow.flow import MethodExecutionStartedEvent, MethodExecutionFinishedEvent, MethodExecutionFailedEvent
    from crewai.utilities.events import crewai_event_bus
    
    @functools.wraps(original_method)
    def sync_wrapper(*args, **kwargs):
        # Emit method started event
        started_event = MethodExecutionStartedEvent(
            method_name=method_name,
            flow_id=flow_id,
            params=kwargs,
            input_state=getattr(flow, 'state', None)
        )
        crewai_event_bus.emit(flow, started_event)
        logger.info(f"📡 Emitted MethodExecutionStartedEvent for: {method_name}")
        
        try:
            # Execute the original method
            result = original_method(*args, **kwargs)
            
            # Emit method finished event
            finished_event = MethodExecutionFinishedEvent(
                method_name=method_name,
                flow_id=flow_id,
                result=result
            )
            crewai_event_bus.emit(flow, finished_event)
            logger.info(f"📡 Emitted MethodExecutionFinishedEvent for: {method_name}")
            
            return result
            
        except Exception as e:
            # Emit method failed event
            failed_event = MethodExecutionFailedEvent(
                method_name=method_name,
                flow_id=flow_id,
                error=str(e)
            )
            crewai_event_bus.emit(flow, failed_event)
            logger.error(f"📡 Emitted MethodExecutionFailedEvent for: {method_name}, error: {e}")
            
            raise
    
    @functools.wraps(original_method)
    async def async_wrapper(*args, **kwargs):
        # Emit method started event
        started_event = MethodExecutionStartedEvent(
            method_name=method_name,
            flow_id=flow_id,
            params=kwargs,
            input_state=getattr(flow, 'state', None)
        )
        crewai_event_bus.emit(flow, started_event)
        logger.info(f"📡 Emitted MethodExecutionStartedEvent for: {method_name}")
        
        try:
            # Execute the original method
            result = await original_method(*args, **kwargs)
            
            # Emit method finished event
            finished_event = MethodExecutionFinishedEvent(
                method_name=method_name,
                flow_id=flow_id,
                result=result
            )
            crewai_event_bus.emit(flow, finished_event)
            logger.info(f"📡 Emitted MethodExecutionFinishedEvent for: {method_name}")
            
            return result
            
        except Exception as e:
            # Emit method failed event
            failed_event = MethodExecutionFailedEvent(
                method_name=method_name,
                flow_id=flow_id,
                error=str(e)
            )
            crewai_event_bus.emit(flow, failed_event)
            logger.error(f"📡 Emitted MethodExecutionFailedEvent for: {method_name}, error: {e}")
            
            raise
    
    # Return appropriate wrapper based on whether original method is async
    if asyncio.iscoroutinefunction(original_method):
        return async_wrapper
    else:
        return sync_wrapper


async def _execute_flow_async(flow_id: str, inputs: Dict[str, Any]):
    """
    Execute a flow asynchronously following the same pattern as crew execution

    Args:
        flow_id: ID of the flow to execute
        inputs: Input parameters for the flow
    """
    logger.info(f"🚀 Starting async execution of flow: {flow_id}")

    try:
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

        # Register flow entity early for proper ID mapping and WebSocket routing
        register_flow_entity(flow, flow_id)
        logger.info(f"Registered flow entity for WebSocket routing: {flow_id}")

        # Run the flow with real-time event emission using custom execution wrapper
        input_dict = inputs or {}
        
        logger.info(f"🚀 FlowHandler: Starting flow execution with inputs: {input_dict}")
        
        # Use custom real-time execution wrapper that emits events as each method executes
        result = await _execute_flow_with_real_time_events(flow, flow_id, input_dict)

        logger.info(f"🎉 Flow execution result type: {type(result)}, status: success")
        return {"status": "success", "result": result}

    except Exception as e:
        error_message = f"Error running flow asynchronously: {str(e)}"
        logger.error(error_message, exc_info=True)
        return {"status": "error", "error": error_message}


@router.post("/{flow_id}/execute")
async def execute_flow(flow_id: str, request: FlowExecuteRequest) -> Dict[str, Any]:
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

        # Set up event listener in the main async context for real-time streaming
        from crewai_playground.events.event_listener import event_listener
        from crewai.utilities.events.crewai_event_bus import crewai_event_bus

        # Ensure event listener has the current event loop
        event_listener.ensure_event_loop()
        event_listener.setup_listeners(crewai_event_bus)

        logger.info(
            f"Event listener setup completed for flow {flow_id}. Event loop: {event_listener.loop}"
        )
        logger.info(f"Connected WebSocket clients: {len(event_listener.clients)}")

        # Run flow execution asynchronously to enable real-time streaming
        async def run_flow_async():
            """Run flow asynchronously to enable real-time WebSocket updates."""
            try:
                logger.info(f"🚀 Starting async flow execution for flow_id: {flow_id}")
                logger.info(
                    f"Event listener clients before execution: {len(event_listener.clients)}"
                )

                # Run the flow using async method to maintain event loop context
                result = await _execute_flow_async(flow_id, request.inputs)

                print(f"Flow execution result: {result}")

                # Safely handle the result
                if result is None:
                    result = {
                        "status": "completed",
                        "message": "Flow execution completed successfully",
                    }
                elif not isinstance(result, dict):
                    result = {"status": "completed", "result": result}

                status = (
                    result.get("status", "completed")
                    if isinstance(result, dict)
                    else "completed"
                )
                logger.info(f"✅ Flow execution completed: {status}")
                logger.info(
                    f"Event listener clients after execution: {len(event_listener.clients)}"
                )
                return result
            except Exception as e:
                logger.error(f"❌ Error in async flow execution: {e}", exc_info=True)
                return {"status": "error", "error": str(e)}

        # Start the async flow execution as a background task
        # This allows the endpoint to return immediately while flow runs in background
        asyncio.create_task(run_flow_async())

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
async def get_flow_traces_route(flow_id: str):
    """Get execution traces for a flow

    Args:
        flow_id: ID of the flow

    Returns:
        List of trace objects with spans structure for visualization
    """
    return await get_flow_traces(flow_id)


@router.post("/{flow_id}/events")
def record_flow_event(flow_id: str, event_type: str, data: Dict[str, Any] = None):
    """Record an event in the flow trace.

    Args:
        flow_id: The flow ID (API flow ID)
        event_type: The type of event (e.g., 'flow_started', 'method_started')
        data: Optional data to include with the event
    """
    if not data:
        data = {}

    # Make sure flow_id is an API flow ID (not an internal flow ID)
    # If it's an internal flow ID, convert it to an API flow ID using entity service
    api_flow_id = entity_service.get_primary_id(flow_id) or flow_id

    # Check if there's a trace for this flow
    if api_flow_id not in flow_traces or not flow_traces[api_flow_id]:
        logger.warning(
            f"No trace found for flow {api_flow_id}, cannot record event {event_type}"
        )
        return

    # Get the latest trace for this flow
    trace = flow_traces[api_flow_id][-1]

    # Add the event to the trace's events array
    event = {
        "type": event_type,
        "timestamp": asyncio.get_event_loop().time(),
        "data": data,
    }

    if "events" not in trace:
        trace["events"] = []

    trace["events"].append(event)
    logger.debug(f"Recorded {event_type} event in trace for flow {api_flow_id}")


async def get_flow_traces(flow_id: str):
    """
    Get execution traces for a flow

    Args:
        flow_id: ID of the flow

    Returns:
        List of trace objects with spans structure for visualization
    """
    logger.info(f"Fetching traces for flow_id: {flow_id}")

    # Check if flow exists in flows_cache
    if flow_id not in flows_cache:
        logger.warning(f"Flow ID {flow_id} not found in flows_cache")

    # Check if flow has any traces
    if flow_id not in flow_traces:
        logger.info(f"No traces found for flow_id: {flow_id}")
        # Create an initializing trace if none exists
        flow_name = flows_cache.get(
            flow_id,
            FlowInfo(
                id=flow_id,
                name="Unknown",
                description="",
                file_path="",
                class_name="",
                flow_class=None,
            ),
        ).name
        initial_trace = {
            "id": f"trace_{uuid.uuid4()}",
            "flow_id": flow_id,
            "flow_name": flow_name,
            "status": "initializing",
            "start_time": datetime.now().timestamp(),
            "spans": [],  # Empty spans array for initialization
            "events": [],
        }
        flow_traces[flow_id] = [initial_trace]
        return {"status": "success", "traces": [initial_trace]}

    # Get flow state to access steps information
    flow_state = flow_states.get(flow_id, {})
    steps = flow_state.get("steps", [])

    # Format flow traces to match the structure expected by TraceTimeline
    formatted_traces = []
    current_time = datetime.now().timestamp()

    for trace in flow_traces[flow_id]:
        try:
            # Create a copy of the trace to avoid modifying the original
            formatted_trace = dict(trace)

            # Validate and fix timestamps
            if (
                formatted_trace.get("start_time") is None
                or formatted_trace.get("start_time") > current_time
            ):
                formatted_trace["start_time"] = (
                    current_time - 60
                )  # Default to 1 minute ago

            # Ensure we have a valid end_time for the trace
            if (
                formatted_trace.get("end_time") is None
                or formatted_trace.get("end_time") > current_time
            ):
                formatted_trace["end_time"] = current_time

            # Create a root span for the flow execution
            trace_id = formatted_trace.get("id", str(uuid.uuid4()))
            root_span = {
                "id": trace_id,
                "name": formatted_trace.get("flow_name", "Flow Execution"),
                "start_time": formatted_trace.get("start_time"),
                "end_time": formatted_trace.get("end_time"),
                "status": formatted_trace.get("status", "initializing"),
                "children": [],
                "attributes": {
                    "flow_id": flow_id,
                    "inputs": formatted_trace.get("inputs", {}),
                },
            }

            # Create some dummy method steps if this is a completed trace with no steps
            # This ensures we have visualization data even for older traces
            use_dummy_steps = (
                formatted_trace.get("status") == "completed"
                and len(steps) == 0
                and formatted_trace.get("start_time")
                and formatted_trace.get("end_time")
            )

            if use_dummy_steps:
                # Create dummy steps based on the flow start and end time
                start_time = formatted_trace.get("start_time")
                end_time = formatted_trace.get("end_time")
                duration = end_time - start_time

                # Create some representative method steps
                dummy_steps = [
                    {
                        "id": f"{trace_id}_method_1",
                        "name": "initialize",
                        "status": "completed",
                        "start_time": start_time + (duration * 0.05),
                        "end_time": start_time + (duration * 0.15),
                        "outputs": "Flow initialized",
                    },
                    {
                        "id": f"{trace_id}_method_2",
                        "name": "process",
                        "status": "completed",
                        "start_time": start_time + (duration * 0.2),
                        "end_time": start_time + (duration * 0.8),
                        "outputs": "Flow processing complete",
                    },
                    {
                        "id": f"{trace_id}_method_3",
                        "name": "finalize",
                        "status": "completed",
                        "start_time": start_time + (duration * 0.85),
                        "end_time": start_time + (duration * 0.95),
                        "outputs": "Flow finalized",
                    },
                ]

                # Use these dummy steps instead of the empty flow state steps
                steps = dummy_steps

            # Process steps and events into spans
            spans = [root_span]  # Start with just the root span

            # Add each step as a child span of the root span
            for step in steps:
                # Use the step's actual timing information or generate meaningful defaults
                step_start = step.get("start_time")
                if step_start is None or step_start > current_time:
                    # Default to 1ms after the root start if no timestamp
                    step_start = root_span["start_time"] + 0.001

                step_end = step.get("end_time")
                if step_end is None or step_end > current_time:
                    # If we have a start but no end, use current time or root end
                    if step.get("status") in ["completed", "failed"]:
                        # For completed/failed steps without end time, use 1ms before root end
                        step_end = root_span["end_time"] - 0.001
                    else:
                        # For running/pending steps, use current time
                        step_end = current_time

                step_span = {
                    "id": step.get("id", str(uuid.uuid4())),
                    "name": step.get("name", "Unknown Method"),
                    "parent_id": root_span["id"],
                    "start_time": step_start,
                    "end_time": step_end,
                    "status": step.get("status", "unknown"),
                    "children": [],
                    "attributes": {
                        "outputs": step.get("outputs"),
                        "error": step.get("error"),
                    },
                }
                spans.append(step_span)  # Add to flat spans list
                root_span["children"].append(step_span)  # Add to hierarchy

            # Add events as additional spans if they're not already represented
            for event in formatted_trace.get("events", []):
                if event.get("type") == "status_change":
                    continue  # Skip status change events as they're already represented

                event_time = event.get("timestamp")
                if event_time is None or event_time > current_time:
                    event_time = root_span["start_time"] + 0.0005

                # Create a span for this event
                event_id = f"{trace_id}_event_{uuid.uuid4().hex[:8]}"
                event_span = {
                    "id": event_id,
                    "name": f"Event: {event.get('type', 'unknown')}",
                    "parent_id": root_span["id"],
                    "start_time": event_time,
                    "end_time": event_time + 0.0001,  # Very short duration for events
                    "status": "completed",
                    "children": [],
                    "attributes": event.get("data", {}),
                }
                spans.append(event_span)  # Add to flat spans list
                root_span["children"].append(event_span)  # Add to hierarchy

            # Replace nodes, edges with properly structured spans
            formatted_trace["spans"] = spans

            # Remove fields that aren't used by the visualization
            if "nodes" in formatted_trace:
                del formatted_trace["nodes"]
            if "edges" in formatted_trace:
                del formatted_trace["edges"]

            formatted_traces.append(formatted_trace)
        except Exception as e:
            logger.error(f"Error formatting trace: {e}", exc_info=True)
            # Skip this trace if there was an error

    logger.info(f"Formatted {len(formatted_traces)} traces for flow_id: {flow_id}")
    return {"status": "success", "traces": formatted_traces}


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
    # Use the event_listener's flow state cache
    from crewai_playground.events.event_listener import (
        event_listener as flow_websocket_listener,
    )

    return flow_websocket_listener.get_flow_state(flow_id)
