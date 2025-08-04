"""
Telemetry service for CrewAI Playground using OpenTelemetry.

This module provides OpenTelemetry integration for tracing CrewAI executions.
"""

import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
import uuid

from crewai_playground.services.entities import entity_service

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.trace.span import Span

# AI SpanAttributes not available in this version of OpenTelemetry
from opentelemetry.semconv.trace import SpanAttributes

# Configure logging
logger = logging.getLogger(__name__)

# In-memory storage for traces
traces_storage: Dict[str, Dict[str, Any]] = {}

# In-memory storage for flow traces
flow_traces_storage: Dict[str, Dict[str, Any]] = {}


class CrewAITelemetry:
    """Telemetry service for CrewAI executions."""

    def __init__(self):
        """Initialize the telemetry service."""
        # Set up the tracer provider only if not already set
        if not trace.get_tracer_provider().__class__.__module__.startswith(
            "opentelemetry.sdk"
        ):
            logger.info("Initializing OpenTelemetry TracerProvider")
            resource = Resource.create({"service.name": "crewai-playground"})
            trace.set_tracer_provider(TracerProvider(resource=resource))
        else:
            logger.info("Using existing OpenTelemetry TracerProvider")

        # Try to set up OTLP exporter if endpoint is available
        # Check if collector is available before attempting to connect
        import socket

        collector_available = False
        try:
            # Try to connect to the collector with a short timeout
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.1)  # 100ms timeout
            s.connect(("localhost", 4318))
            s.close()
            collector_available = True
        except (socket.timeout, socket.error, ConnectionRefusedError):
            logger.info(
                "OpenTelemetry collector not available at localhost:4318, using console exporter only"
            )

        if collector_available:
            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint="http://localhost:4318/v1/traces"
                )
                trace.get_tracer_provider().add_span_processor(
                    BatchSpanProcessor(otlp_exporter)
                )
                logger.info("Successfully connected to OpenTelemetry collector")
            except Exception as e:
                logger.warning(f"Failed to set up OTLP exporter: {e}")

        self.tracer = trace.get_tracer("crewai.telemetry")
        self.active_spans: Dict[str, Span] = {}
        # Map crew_id -> currently active trace id (latest run)
        self._current_trace_for_crew: Dict[str, str] = {}

    def _get_trace_id_for_crew(
        self, crew_id: str, prefer_running: bool = True
    ) -> Optional[str]:
        """Return the trace id that should be used for this crew.

        If *prefer_running* is True, the most recent trace whose status is not
        "completed" is returned. Otherwise the most recent trace regardless of
        status is returned.  A *None* is returned when no trace exists for the
        crew.
        """
        # 1. Fast path – did we record the id when the trace was started?
        cached = self._current_trace_for_crew.get(crew_id)
        if cached and cached in traces_storage:
            if not prefer_running or traces_storage[cached]["status"] != "completed":
                return cached

        # 2. Use entity service to resolve all possible crew IDs
        possible_crew_ids = entity_service.resolve_broadcast_ids(crew_id)
        logger.info(f"Looking for traces with possible crew IDs: {possible_crew_ids}")

        # Scan storage to find all traces for any of the possible crew IDs
        candidates = []
        for tid, tdata in traces_storage.items():
            stored_crew_id = str(tdata.get("crew_id", ""))
            if stored_crew_id in possible_crew_ids:
                candidates.append((tid, tdata))
                logger.info(f"Found matching trace with crew_id {stored_crew_id}")

        # Fallback to direct string comparison if entity service doesn't have mappings
        if not candidates:
            logger.info(
                f"No matches found with entity service, falling back to direct comparison"
            )
            candidates = [
                (tid, tdata)
                for tid, tdata in traces_storage.items()
                if str(tdata.get("crew_id")) == str(crew_id)
            ]
        if not candidates:
            return None

        # Prefer running traces
        if prefer_running:
            running = [c for c in candidates if c[1].get("status") != "completed"]
            if running:
                # choose latest by start_time
                running.sort(key=lambda x: x[1].get("start_time", ""))
                trace_id = running[-1][0]
                self._current_trace_for_crew[crew_id] = trace_id
                return trace_id

        # Fallback: choose latest by start_time
        candidates.sort(key=lambda x: x[1].get("start_time", ""))
        trace_id = candidates[-1][0]
        self._current_trace_for_crew[crew_id] = trace_id
        return trace_id

    def start_crew_trace(self, crew_id: str, crew_name: str) -> str:
        """Start a new trace for a crew execution.

        Args:
            crew_id: The ID of the crew
            crew_name: The name of the crew

        Returns:
            The ID of the trace
        """
        # Ensure crew_id is a string
        crew_id = str(crew_id).strip()

        logger.info(f"Starting trace for crew_id: {crew_id}, crew_name: {crew_name}")
        logger.info(f"Current traces in storage: {len(traces_storage)}")

        # Register entity mapping for this crew to ensure proper ID resolution
        try:
            entity_service.register_entity(
                primary_id=crew_id,
                internal_id=crew_id,  # Use same ID as both primary and internal for now
                entity_type="crew",
                name=crew_name,
            )
            logger.info(
                f"Registered entity mapping for crew: {crew_id}, name: {crew_name}"
            )
        except Exception as e:
            logger.warning(f"Failed to register entity mapping: {e}")
            # Continue even if registration fails

        trace_id = str(uuid.uuid4())
        with self.tracer.start_as_current_span(
            name=f"crew.execute.{crew_name}",
            attributes={
                "llm.workflow.name": crew_name,
                "llm.workflow.id": crew_id,
                "crew.id": crew_id,
                "crew.name": crew_name,
            },
        ) as span:
            span_context = span.get_span_context()
            trace_id = format(span_context.trace_id, "032x")

            # Store the trace in memory
            traces_storage[trace_id] = {
                "id": trace_id,
                "crew_id": crew_id,
                "crew_name": crew_name,
                "start_time": datetime.utcnow().isoformat(),
                "status": "running",
                "events": [],
                "agents": {},
                "tasks": {},
            }

            # Store the active span
            self.active_spans[crew_id] = span
            # Remember this trace as the current active one for the crew
            self._current_trace_for_crew[crew_id] = trace_id

            logger.info(f"Started trace with ID: {trace_id} for crew_id: {crew_id}")
            logger.info(f"Total traces in storage: {len(traces_storage)}")
        return trace_id

    def end_crew_trace(self, crew_id: str, output: Any = None):
        """End a trace for a crew execution.

        Args:
            crew_id: The ID of the crew
            output: The output of the crew execution
        """
        # Ensure crew_id is a string
        crew_id = str(crew_id).strip()

        logger.info(f"Ending trace for crew_id: {crew_id}")

        # Locate the most relevant trace for this crew (prefer running)
        trace_id = self._get_trace_id_for_crew(crew_id)

        if not trace_id:
            logger.error(f"No trace found for crew_id: {crew_id}")
            return

        logger.info(f"Found trace with ID: {trace_id} for crew_id: {crew_id}")

        # Update the trace with the output
        if output:
            try:
                output_text = output.raw if hasattr(output, "raw") else str(output)
                logger.info(f"Output length: {len(output_text) if output_text else 0}")
                traces_storage[trace_id]["output"] = output_text
            except Exception as e:
                logger.warning(f"Failed to convert output to string: {e}")
                traces_storage[trace_id]["output"] = "Output conversion failed"

        # Mark the trace as completed
        traces_storage[trace_id]["status"] = "completed"
        traces_storage[trace_id]["end_time"] = datetime.utcnow().isoformat()

        # End the span if it exists
        if crew_id in self.active_spans:
            self.active_spans[crew_id].end()
            del self.active_spans[crew_id]

        logger.info(f"Completed trace with ID: {trace_id} for crew_id: {crew_id}")

    def start_agent_execution(
        self, crew_id: str, agent_id: str, agent_name: str, agent_role: str
    ):
        """Start tracing an agent execution.

        Args:
            crew_id: The ID of the crew
            agent_id: The ID of the agent
            agent_name: The name of the agent
            agent_role: The role of the agent
        """
        # Safety check: ensure agent_id is not None or empty
        if not agent_id or agent_id == "None":
            logger.warning(f"Invalid agent_id '{agent_id}' for crew {crew_id}, using fallback")
            agent_id = f"agent_unknown_{abs(hash(agent_name or agent_role or 'unknown')) % 100000}"
        
        # Locate active trace for this crew
        trace_id = self._get_trace_id_for_crew(crew_id)

        if not trace_id:
            logger.warning(f"No trace found for crew {crew_id}")
            return

        # Add the agent to the trace
        if agent_id not in traces_storage[trace_id]["agents"]:
            traces_storage[trace_id]["agents"][agent_id] = {
                "id": agent_id,
                "name": agent_name,
                "role": agent_role,
                "status": "running",
                "start_time": datetime.utcnow().isoformat(),
                "events": [],
            }
        else:
            # Update the agent status
            traces_storage[trace_id]["agents"][agent_id]["status"] = "running"
            traces_storage[trace_id]["agents"][agent_id][
                "start_time"
            ] = datetime.utcnow().isoformat()

        # Add an event
        self.add_event(
            crew_id,
            "agent.started",
            {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_role": agent_role,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Create a span for the agent execution
        parent_span = self.active_spans.get(crew_id)
        if parent_span:
            with self.tracer.start_as_current_span(
                name=f"agent.execute.{agent_role}",
                attributes={
                    "llm.user.role": agent_role or "unknown",
                    "llm.user.id": agent_id or "unknown",
                    "agent.id": agent_id or "unknown",
                    "agent.name": agent_name or "unknown",
                    "agent.role": agent_role or "unknown",
                },
            ) as span:
                # Store the active span
                self.active_spans[agent_id] = span

    def end_agent_execution(self, crew_id: str, agent_id: str, output: Any = None):
        """End tracing an agent execution.

        Args:
            crew_id: The ID of the crew
            agent_id: The ID of the agent
            output: The output of the agent execution
        """
        # Safety check: ensure agent_id is not None or empty
        if not agent_id or agent_id == "None":
            logger.warning(f"Invalid agent_id '{agent_id}' for crew {crew_id} in end_agent_execution")
            return  # Can't end execution for unknown agent
        
        # Locate active trace for this crew
        trace_id = self._get_trace_id_for_crew(crew_id)

        if not trace_id:
            logger.warning(f"No trace found for crew {crew_id}")
            return

        # Update the agent status
        if agent_id in traces_storage[trace_id]["agents"]:
            traces_storage[trace_id]["agents"][agent_id]["status"] = "completed"
            traces_storage[trace_id]["agents"][agent_id][
                "end_time"
            ] = datetime.utcnow().isoformat()

            # Add the output
            if output:
                try:
                    # Try to convert to string if it's not already
                    if not isinstance(output, str):
                        output_str = str(output)
                    else:
                        output_str = output

                    traces_storage[trace_id]["agents"][agent_id]["output"] = output_str
                except Exception as e:
                    logger.warning(f"Failed to convert output to string: {e}")
                    traces_storage[trace_id]["agents"][agent_id][
                        "output"
                    ] = "Output conversion failed"

        # Add an event
        self.add_event(
            crew_id,
            "agent.completed",
            {"agent_id": agent_id, "timestamp": datetime.utcnow().isoformat()},
        )

        # End the span
        if agent_id in self.active_spans:
            self.active_spans[agent_id].end()
            del self.active_spans[agent_id]

    def start_task_execution(
        self,
        crew_id: str,
        task_id: str,
        task_description: str,
        agent_id: Optional[str] = None,
    ):
        """Start tracing a task execution.

        Args:
            crew_id: The ID of the crew
            task_id: The ID of the task
            task_description: The description of the task
            agent_id: The ID of the agent executing the task
        """
        # Safety check: ensure task_id is not None or empty
        if not task_id or task_id == "None":
            logger.warning(f"Invalid task_id '{task_id}' for crew {crew_id}, using fallback")
            task_id = f"task_unknown_{abs(hash(task_description or 'unknown')) % 100000}"
        
        # Locate active trace for this crew
        trace_id = self._get_trace_id_for_crew(crew_id)

        if not trace_id:
            logger.warning(f"No trace found for crew {crew_id}")
            return

        # Add the task to the trace
        if task_id not in traces_storage[trace_id]["tasks"]:
            traces_storage[trace_id]["tasks"][task_id] = {
                "id": task_id,
                "description": task_description,
                "agent_id": agent_id,
                "status": "running",
                "start_time": datetime.utcnow().isoformat(),
                "events": [],
            }
        else:
            # Update the task status
            traces_storage[trace_id]["tasks"][task_id]["status"] = "running"
            traces_storage[trace_id]["tasks"][task_id][
                "start_time"
            ] = datetime.utcnow().isoformat()

            # Update the agent ID if provided
            if agent_id:
                traces_storage[trace_id]["tasks"][task_id]["agent_id"] = agent_id

        # Add an event
        self.add_event(
            crew_id,
            "task.started",
            {
                "task_id": task_id,
                "task_description": task_description,
                "agent_id": agent_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Create a span for the task execution
        parent_span = (
            self.active_spans.get(agent_id)
            if agent_id
            else self.active_spans.get(crew_id)
        )
        if parent_span:
            with self.tracer.start_as_current_span(
                name=f"task.execute",
                attributes={
                    "task.id": task_id or "unknown",
                    "task.description": task_description or "unknown",
                    "agent.id": agent_id or "unknown",
                },
            ) as span:
                # Store the active span
                self.active_spans[task_id] = span

    def end_task_execution(self, crew_id: str, task_id: str, output: Any = None):
        """End tracing a task execution.

        Args:
            crew_id: The ID of the crew
            task_id: The ID of the task
            output: The output of the task execution
        """
        # Safety check for task_id
        if not task_id or task_id == "None":
            task_id = f"task_unknown_{abs(hash(str(output) or 'unknown')) % 100000}"
            logger.warning(f"Invalid task_id provided to end_task_execution, using fallback: {task_id}")
        
        # Locate active trace for this crew
        trace_id = self._get_trace_id_for_crew(crew_id)

        if not trace_id:
            logger.warning(f"No trace found for crew {crew_id}")
            return

        # Update the task status
        if task_id in traces_storage[trace_id]["tasks"]:
            traces_storage[trace_id]["tasks"][task_id]["status"] = "completed"
            traces_storage[trace_id]["tasks"][task_id][
                "end_time"
            ] = datetime.utcnow().isoformat()

            # Add the output
            if output:
                try:
                    # Try to convert to string if it's not already
                    if not isinstance(output, str):
                        output_str = str(output)
                    else:
                        output_str = output

                    traces_storage[trace_id]["tasks"][task_id]["output"] = output_str
                except Exception as e:
                    logger.warning(f"Failed to convert output to string: {e}")
                    traces_storage[trace_id]["tasks"][task_id][
                        "output"
                    ] = "Output conversion failed"

        # Add an event
        self.add_event(
            crew_id,
            "task.completed",
            {"task_id": task_id, "timestamp": datetime.utcnow().isoformat()},
        )

        # End the span
        if task_id in self.active_spans:
            self.active_spans[task_id].end()
            del self.active_spans[task_id]

    def trace_tool_execution(
        self,
        crew_id: str,
        agent_id: Optional[str],
        tool_name: str,
        inputs: Dict[str, Any],
        output: Any = None,
    ):
        """Trace a tool execution.

        Args:
            crew_id: The ID of the crew
            agent_id: The ID of the agent executing the tool
            tool_name: The name of the tool
            inputs: The inputs to the tool
            output: The output of the tool execution
        """
        # Locate active trace for this crew
        trace_id = self._get_trace_id_for_crew(crew_id)

        if not trace_id:
            logger.warning(f"No trace found for crew {crew_id}")
            return

        # Add an event
        event_data = {
            "tool_name": tool_name,
            "inputs": inputs,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if agent_id:
            event_data["agent_id"] = agent_id

        if output:
            try:
                # Try to convert to string if it's not already
                if not isinstance(output, str):
                    output_str = str(output)
                else:
                    output_str = output

                event_data["output"] = output_str
            except Exception as e:
                logger.warning(f"Failed to convert output to string: {e}")
                event_data["output"] = "Output conversion failed"

        self.add_event(crew_id, "tool.executed", event_data)

        # Create a span for the tool execution
        parent_span = None
        if agent_id and agent_id in self.active_spans:
            parent_span = self.active_spans[agent_id]
        elif crew_id in self.active_spans:
            parent_span = self.active_spans[crew_id]

        if parent_span:
            with self.tracer.start_as_current_span(
                name=f"tool.execute.{tool_name}",
                attributes={
                    "tool.name": tool_name,
                    "tool.inputs": json.dumps(inputs),
                    "agent.id": agent_id if agent_id else "unknown",
                },
            ) as span:
                # Add the output to the span
                if output:
                    try:
                        if isinstance(output, str):
                            span.set_attribute("tool.output", output)
                        else:
                            span.set_attribute("tool.output", str(output))
                    except Exception:
                        span.set_attribute("tool.output", "Output conversion failed")

    def add_event(self, crew_id: str, event_type: str, event_data: Dict[str, Any]):
        """Add an event to a trace.

        Args:
            crew_id: The ID of the crew
            event_type: The type of event
            event_data: The event data
        """
        # Locate active trace for this crew
        trace_id = self._get_trace_id_for_crew(crew_id)

        if not trace_id:
            logger.warning(f"No trace found for crew {crew_id}")
            return

        # Add the event to the trace
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": event_data,
        }
        traces_storage[trace_id]["events"].append(event)

        # If the event is related to an agent, add it to the agent's events
        if (
            "agent_id" in event_data
            and event_data["agent_id"] in traces_storage[trace_id]["agents"]
        ):
            traces_storage[trace_id]["agents"][event_data["agent_id"]]["events"].append(
                event
            )

        # If the event is related to a task, add it to the task's events
        if (
            "task_id" in event_data
            and event_data["task_id"] in traces_storage[trace_id]["tasks"]
        ):
            traces_storage[trace_id]["tasks"][event_data["task_id"]]["events"].append(
                event
            )

    def get_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent traces.

        Args:
            limit: The maximum number of traces to return

        Returns:
            A list of traces
        """
        # Sort traces by start time (newest first)
        sorted_traces = sorted(
            traces_storage.values(), key=lambda t: t.get("start_time", ""), reverse=True
        )

        # Return the most recent traces
        return sorted_traces[:limit]

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific trace by ID.

        Args:
            trace_id: The ID of the trace

        Returns:
            The trace data or None if not found
        """
        return traces_storage.get(trace_id)

    def get_traces_for_crew(self, crew_id: str) -> List[Dict[str, Any]]:
        """Get all traces for a specific crew.

        Args:
            crew_id: The ID of the crew

        Returns:
            A list of traces for the crew
        """
        logger.info(f"Looking for traces with crew_id: {crew_id}")
        logger.info(f"Current traces in storage: {len(traces_storage)}")

        # Normalize the crew ID for comparison
        normalized_crew_id = str(crew_id).strip().lower()

        # Debug: Log all crew IDs in storage
        all_crew_ids = set(trace.get("crew_id") for trace in traces_storage.values())
        logger.info(f"Available crew IDs in storage: {all_crew_ids}")

        # Use entity service to resolve all possible crew IDs
        possible_crew_ids = entity_service.resolve_broadcast_ids(crew_id)
        logger.info(f"Looking for traces with possible crew IDs: {possible_crew_ids}")

        # Find traces that match any of the possible crew IDs
        traces = []
        for trace in traces_storage.values():
            stored_crew_id = str(trace.get("crew_id", ""))
            if stored_crew_id in possible_crew_ids:
                traces.append(trace)
                logger.info(f"Found matching trace with crew_id {stored_crew_id}")

        # If no matches found with entity service, fall back to original methods
        if not traces:
            logger.info(
                f"No matches found with entity service, falling back to direct comparison"
            )

            # Try exact match first
            traces = [
                trace
                for trace in traces_storage.values()
                if trace.get("crew_id") == crew_id
            ]

            # If no exact matches, try case-insensitive comparison
            if not traces:
                logger.info(
                    f"No exact matches found, trying case-insensitive comparison for: {crew_id}"
                )
                traces = [
                    trace
                    for trace in traces_storage.values()
                    if trace.get("crew_id")
                    and str(trace.get("crew_id")).strip().lower() == normalized_crew_id
                ]

            # If still no matches and crew_id looks like a simple name (e.g., "crew_0"), try to find any trace
            # that might contain this as part of the crew name
            if not traces and ("_" in crew_id or crew_id.isalnum()):
                logger.info(
                    f"No matches found, trying to match by crew name pattern: {crew_id}"
                )
                traces = [
                    trace
                    for trace in traces_storage.values()
                    if trace.get("crew_name")
                    and crew_id.lower() in str(trace.get("crew_name")).lower()
                ]

            # If we found traces by name pattern, log this information
            if traces:
                logger.info(
                    f"Found {len(traces)} traces by matching crew name pattern: {crew_id}"
                )
                # Log the actual crew IDs that were matched
                matched_ids = set(trace.get("crew_id") for trace in traces)
                logger.info(f"Matched crew IDs: {matched_ids}")

        logger.info(f"Found {len(traces)} traces for crew_id: {crew_id}")
        return traces

    # Flow Trace Methods
    def start_flow_trace(self, flow_id: str, flow_name: str) -> str:
        """Start a new trace for a flow execution.

        Args:
            flow_id: The ID of the flow
            flow_name: The name of the flow

        Returns:
            The ID of the trace
        """
        # Ensure flow_id is a string
        flow_id = str(flow_id).strip()

        logger.info(f"Starting flow trace for flow_id: {flow_id}, flow_name: {flow_name}")
        logger.info(f"Current flow traces in storage: {len(flow_traces_storage)}")

        # Register entity mapping for this flow to ensure proper ID resolution
        try:
            entity_service.register_entity(
                primary_id=flow_id,
                internal_id=flow_id,  # Use same ID as both primary and internal for now
                entity_type="flow",
                name=flow_name,
            )
            logger.info(
                f"Registered entity mapping for flow: {flow_id}, name: {flow_name}"
            )
        except Exception as e:
            logger.warning(f"Failed to register flow entity mapping: {e}")
            # Continue even if registration fails

        trace_id = str(uuid.uuid4())
        with self.tracer.start_as_current_span(
            name=f"flow.execute.{flow_name}",
            attributes={
                "llm.workflow.name": flow_name,
                "llm.workflow.id": flow_id,
                "flow.id": flow_id,
                "flow.name": flow_name,
            },
        ) as span:
            span_context = span.get_span_context()
            trace_id = format(span_context.trace_id, "032x")

            # Store the flow trace in memory with comprehensive structure
            flow_traces_storage[trace_id] = {
                "id": trace_id,
                "flow_id": flow_id,
                "flow_name": flow_name,
                "start_time": datetime.utcnow().isoformat(),
                "status": "running",
                "events": [],
                "crews": {},  # Crews executed within this flow
                "agents": {},  # Agents from all crews in this flow
                "tasks": {},   # Tasks from all crews in this flow
                "methods": {}, # Flow methods executed
                "llm_calls": [],  # LLM calls made during flow execution
                "tool_executions": [],  # Tool executions during flow
            }

            # Store the active span
            self.active_spans[flow_id] = span
            # Remember this trace as the current active one for the flow
            self._current_trace_for_crew[flow_id] = trace_id  # Reuse crew mapping for flows

            logger.info(f"Started flow trace with ID: {trace_id} for flow_id: {flow_id}")
            logger.info(f"Total flow traces in storage: {len(flow_traces_storage)}")
        return trace_id

    def end_flow_trace(self, flow_id: str, output: Any = None):
        """End a trace for a flow execution.

        Args:
            flow_id: The ID of the flow
            output: The output of the flow execution
        """
        # Ensure flow_id is a string
        flow_id = str(flow_id).strip()

        logger.info(f"Ending flow trace for flow_id: {flow_id}")

        # Find the trace for this flow
        trace_id = None
        for tid, tdata in flow_traces_storage.items():
            if str(tdata.get("flow_id", "")).strip() == flow_id:
                trace_id = tid
                break

        if not trace_id:
            logger.error(f"No flow trace found for flow_id: {flow_id}")
            return

        logger.info(f"Found flow trace with ID: {trace_id} for flow_id: {flow_id}")

        # Update the trace with the output
        if output:
            try:
                output_text = output.raw if hasattr(output, "raw") else str(output)
                logger.info(f"Flow output length: {len(output_text) if output_text else 0}")
                flow_traces_storage[trace_id]["output"] = output_text
            except Exception as e:
                logger.warning(f"Failed to convert flow output to string: {e}")
                flow_traces_storage[trace_id]["output"] = "Output conversion failed"

        # Mark the trace as completed
        flow_traces_storage[trace_id]["status"] = "completed"
        flow_traces_storage[trace_id]["end_time"] = datetime.utcnow().isoformat()

        # End the span if it exists
        if flow_id in self.active_spans:
            self.active_spans[flow_id].end()
            del self.active_spans[flow_id]

        logger.info(f"Completed flow trace with ID: {trace_id} for flow_id: {flow_id}")

    def add_flow_method_execution(self, flow_id: str, method_name: str, status: str, 
                                 outputs: Any = None, error: str = None):
        """Add a method execution to a flow trace.

        Args:
            flow_id: The ID of the flow
            method_name: The name of the method
            status: The status of the method execution (started, completed, failed)
            outputs: The outputs of the method execution
            error: Error message if the method failed
        """
        # Find the trace for this flow
        trace_id = None
        for tid, tdata in flow_traces_storage.items():
            if str(tdata.get("flow_id", "")).strip() == str(flow_id).strip():
                trace_id = tid
                break

        if not trace_id:
            logger.warning(f"No flow trace found for flow_id: {flow_id}")
            return

        method_id = f"{method_name}_{uuid.uuid4().hex[:8]}"
        
        # Add or update the method in the trace
        if method_id not in flow_traces_storage[trace_id]["methods"]:
            flow_traces_storage[trace_id]["methods"][method_id] = {
                "id": method_id,
                "name": method_name,
                "status": status,
                "start_time": datetime.utcnow().isoformat(),
                "events": [],
            }
        else:
            flow_traces_storage[trace_id]["methods"][method_id]["status"] = status

        # Update method details based on status
        if status == "completed":
            flow_traces_storage[trace_id]["methods"][method_id]["end_time"] = datetime.utcnow().isoformat()
            if outputs:
                try:
                    outputs_str = outputs if isinstance(outputs, str) else str(outputs)
                    flow_traces_storage[trace_id]["methods"][method_id]["outputs"] = outputs_str
                except Exception as e:
                    logger.warning(f"Failed to convert method outputs to string: {e}")
                    flow_traces_storage[trace_id]["methods"][method_id]["outputs"] = "Output conversion failed"
        elif status == "failed":
            flow_traces_storage[trace_id]["methods"][method_id]["end_time"] = datetime.utcnow().isoformat()
            flow_traces_storage[trace_id]["methods"][method_id]["error"] = error or "Method execution failed"

        # Add an event
        self.add_flow_event(
            flow_id,
            f"method.{status}",
            {
                "method_id": method_id,
                "method_name": method_name,
                "timestamp": datetime.utcnow().isoformat(),
                "outputs": outputs,
                "error": error,
            },
        )

    def add_flow_crew_execution(self, flow_id: str, crew_id: str, crew_name: str, 
                               status: str, agents: List[Dict] = None, tasks: List[Dict] = None):
        """Add a crew execution to a flow trace.

        Args:
            flow_id: The ID of the flow
            crew_id: The ID of the crew
            crew_name: The name of the crew
            status: The status of the crew execution
            agents: List of agent information
            tasks: List of task information
        """
        # Find the trace for this flow
        trace_id = None
        for tid, tdata in flow_traces_storage.items():
            if str(tdata.get("flow_id", "")).strip() == str(flow_id).strip():
                trace_id = tid
                break

        if not trace_id:
            logger.warning(f"No flow trace found for flow_id: {flow_id}")
            return

        # Add or update the crew in the trace
        if crew_id not in flow_traces_storage[trace_id]["crews"]:
            flow_traces_storage[trace_id]["crews"][crew_id] = {
                "id": crew_id,
                "name": crew_name,
                "status": status,
                "start_time": datetime.utcnow().isoformat(),
                "events": [],
            }
        else:
            flow_traces_storage[trace_id]["crews"][crew_id]["status"] = status

        # Add agents to the flow trace
        if agents:
            for agent in agents:
                agent_id = agent.get("id", f"agent_{uuid.uuid4().hex[:8]}")
                flow_traces_storage[trace_id]["agents"][agent_id] = {
                    "id": agent_id,
                    "name": agent.get("name", "Unknown Agent"),
                    "role": agent.get("role", "Unknown Role"),
                    "crew_id": crew_id,
                    "status": "initializing",
                    "events": [],
                }

        # Add tasks to the flow trace
        if tasks:
            for task in tasks:
                task_id = task.get("id", f"task_{uuid.uuid4().hex[:8]}")
                flow_traces_storage[trace_id]["tasks"][task_id] = {
                    "id": task_id,
                    "description": task.get("description", "Unknown Task"),
                    "crew_id": crew_id,
                    "agent_id": task.get("agent_id"),
                    "status": "pending",
                    "events": [],
                }

        # Add an event
        self.add_flow_event(
            flow_id,
            f"crew.{status}",
            {
                "crew_id": crew_id,
                "crew_name": crew_name,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def add_flow_event(self, flow_id: str, event_type: str, event_data: Dict[str, Any] = None):
        """Add an event to a flow trace.

        Args:
            flow_id: The ID of the flow
            event_type: The type of event
            event_data: The event data
        """
        # Find the trace for this flow
        trace_id = None
        for tid, tdata in flow_traces_storage.items():
            if str(tdata.get("flow_id", "")).strip() == str(flow_id).strip():
                trace_id = tid
                break

        if not trace_id:
            logger.warning(f"No flow trace found for flow_id: {flow_id}")
            return

        # Add the event to the trace
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": event_data or {},
        }
        flow_traces_storage[trace_id]["events"].append(event)

        # If the event is related to an agent, add it to the agent's events
        if (
            "agent_id" in event_data
            and event_data["agent_id"] in flow_traces_storage[trace_id]["agents"]
        ):
            flow_traces_storage[trace_id]["agents"][event_data["agent_id"]]["events"].append(
                event
            )

        # If the event is related to a task, add it to the task's events
        if (
            "task_id" in event_data
            and event_data["task_id"] in flow_traces_storage[trace_id]["tasks"]
        ):
            flow_traces_storage[trace_id]["tasks"][event_data["task_id"]]["events"].append(
                event
            )

        # If the event is related to a crew, add it to the crew's events
        if (
            "crew_id" in event_data
            and event_data["crew_id"] in flow_traces_storage[trace_id]["crews"]
        ):
            flow_traces_storage[trace_id]["crews"][event_data["crew_id"]]["events"].append(
                event
            )

    def get_flow_traces(self, flow_id: str) -> List[Dict[str, Any]]:
        """Get all traces for a specific flow.

        Args:
            flow_id: The ID of the flow

        Returns:
            A list of flow traces
        """
        flow_id = str(flow_id).strip()
        logger.info(f"Getting flow traces for flow_id: {flow_id}")
        
        # Use entity service to resolve possible flow IDs
        possible_flow_ids = entity_service.resolve_broadcast_ids(flow_id)
        logger.info(f"Looking for flow traces with possible flow IDs: {possible_flow_ids}")
        
        traces = []
        for trace in flow_traces_storage.values():
            stored_flow_id = str(trace.get("flow_id", ""))
            if stored_flow_id in possible_flow_ids:
                traces.append(trace)
                logger.info(f"Found matching flow trace with flow_id {stored_flow_id}")
        
        logger.info(f"Found {len(traces)} flow traces for flow_id: {flow_id}")
        return traces

    def get_flow_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific flow trace by ID.

        Args:
            trace_id: The ID of the trace

        Returns:
            The flow trace data or None if not found
        """
        return flow_traces_storage.get(trace_id)


# Create a singleton instance
telemetry_service = CrewAITelemetry()
