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
        # Map flow_id -> currently active trace id (latest run)
        self._current_trace_for_flow: Dict[str, str] = {}
        # Map internal_flow_id -> current trace id (helps dedupe when internal ids are used)
        self._internal_flow_to_trace: Dict[str, str] = {}

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

    def _get_trace_id_for_flow(
        self, flow_id: str, prefer_running: bool = True
    ) -> Optional[str]:
        """Return the trace id that should be used for this flow.

        If *prefer_running* is True, the most recent trace whose status is not
        "completed" is returned. Otherwise the most recent trace regardless of
        status is returned.  A *None* is returned when no trace exists for the
        flow.
        """
        # Ensure flow_id is a string
        flow_id = str(flow_id).strip()
        
        # 1. Fast path – did we record the id when the trace was started?
        cached = self._current_trace_for_flow.get(flow_id)
        if cached and cached in traces_storage:
            if not prefer_running or traces_storage[cached]["status"] != "completed":
                return cached

        # 2. Since flow IDs are now standardized, do direct lookup
        logger.info(f"Looking for traces with standardized flow_id: {flow_id}")

        # Find traces that match the standardized flow ID
        candidates = [
            (tid, tdata)
            for tid, tdata in traces_storage.items()
            if str(tdata.get("flow_id")) == flow_id
        ]
        
        if not candidates:
            logger.info(f"No traces found for flow_id: {flow_id}")
            return None

        # Prefer running traces
        if prefer_running:
            running = [c for c in candidates if c[1].get("status") != "completed"]
            if running:
                # choose latest by start_time
                running.sort(key=lambda x: x[1].get("start_time", ""))
                trace_id = running[-1][0]
                self._current_trace_for_flow[flow_id] = trace_id
                logger.info(f"Found running trace {trace_id} for flow_id: {flow_id}")
                return trace_id

        # Fallback: choose latest by start_time
        candidates.sort(key=lambda x: x[1].get("start_time", ""))
        trace_id = candidates[-1][0]
        self._current_trace_for_flow[flow_id] = trace_id
        logger.info(f"Found latest trace {trace_id} for flow_id: {flow_id}")
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

    def start_flow_trace(
        self, flow_id: str, flow_name: str, internal_flow_id: str = None
    ) -> str:
        """Start a new trace for a flow execution.

        Args:
            flow_id: The standardized flow ID (API UUID)
            flow_name: The name of the flow
            internal_flow_id: Deprecated - no longer used since flow IDs are standardized

        Returns:
            The ID of the trace
        """
        # Ensure flow_id is a string
        flow_id = str(flow_id).strip()

        logger.info(
            f"Starting trace for standardized flow_id: {flow_id}, flow_name: {flow_name}"
        )
        logger.info(f"Current traces in storage: {len(traces_storage)}")

        # --- Duplicate guard: if a running trace already exists, reuse it ---
        try:
            # Check for existing running trace for this flow_id
            existing_trace = self._get_trace_id_for_flow(flow_id, prefer_running=True)
            if (
                existing_trace
                and traces_storage.get(existing_trace, {}).get("status") != "completed"
            ):
                logger.warning(
                    f"Duplicate flow trace start detected for flow_id={flow_id}. Reusing trace_id={existing_trace}"
                )
                # Maintain most recent mapping
                self._current_trace_for_flow[flow_id] = existing_trace
                return existing_trace
        except Exception as dup_err:
            logger.warning(f"Error while checking for duplicate flow trace: {dup_err}")

        # Register entity mapping for this flow to ensure proper ID resolution
        try:
            entity_service.register_entity(
                primary_id=flow_id,  # Standardized flow ID as primary
                internal_id=None,  # No separate internal ID since we standardized
                entity_type="flow",
                name=flow_name,
            )
            logger.info(
                f"Registered entity mapping for standardized flow: flow_id={flow_id}, name={flow_name}"
            )
        except Exception as e:
            logger.warning(f"Failed to register entity mapping: {e}")
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

            # Store the trace in memory with standardized structure
            traces_storage[trace_id] = {
                "id": trace_id,
                "flow_id": flow_id,  # Standardized flow ID (API UUID)
                "flow_name": flow_name,
                "start_time": datetime.utcnow().isoformat(),
                "status": "running",
                "events": [],
                "methods": {},
                "steps": [],
            }

            # Store the active span
            self.active_spans[flow_id] = span
            # Remember this trace as the current active one for the flow
            self._current_trace_for_flow[flow_id] = trace_id

            logger.info(f"Started trace with ID: {trace_id} for flow_id: {flow_id}")
            logger.info(f"Total traces in storage: {len(traces_storage)}")
        return trace_id

    def end_flow_trace(self, flow_id: str, output: Any = None):
        """End a trace for a flow execution.

        Args:
            flow_id: The ID of the flow
            output: The output of the flow execution
        """
        # Ensure flow_id is a string
        flow_id = str(flow_id).strip()

        logger.info(f"Ending trace for flow_id: {flow_id}")

        # Locate the most relevant trace for this flow (prefer running)
        trace_id = self._get_trace_id_for_flow(flow_id)

        if not trace_id:
            logger.error(f"No trace found for flow_id: {flow_id}")
            return

        logger.info(f"Found trace with ID: {trace_id} for flow_id: {flow_id}")

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
        if flow_id in self.active_spans:
            self.active_spans[flow_id].end()
            del self.active_spans[flow_id]

        logger.info(f"Completed trace with ID: {trace_id} for flow_id: {flow_id}")

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
            logger.warning(
                f"Invalid agent_id '{agent_id}' for crew {crew_id}, using fallback"
            )
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
            logger.warning(
                f"Invalid agent_id '{agent_id}' for crew {crew_id} in end_agent_execution"
            )
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
            logger.warning(
                f"Invalid task_id '{task_id}' for crew {crew_id}, using fallback"
            )
            task_id = (
                f"task_unknown_{abs(hash(task_description or 'unknown')) % 100000}"
            )

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
            logger.warning(
                f"Invalid task_id provided to end_task_execution, using fallback: {task_id}"
            )

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

    def get_traces_for_flow(self, flow_id: str) -> List[Dict[str, Any]]:
        """Get all traces for a specific flow.

        Args:
            flow_id: The standardized flow ID (API UUID)

        Returns:
            A list of traces for the flow
        """
        # Ensure flow_id is a string
        flow_id = str(flow_id).strip()
        
        logger.info(f"Looking for traces with standardized flow_id: {flow_id}")
        logger.info(f"Current traces in storage: {len(traces_storage)}")

        # Debug: Log all flow IDs in storage
        all_flow_ids = set(trace.get("flow_id") for trace in traces_storage.values())
        logger.info(f"Available flow IDs in storage: {all_flow_ids}")

        # Since flow IDs are now standardized, do direct lookup
        traces = [
            trace
            for trace in traces_storage.values()
            if str(trace.get("flow_id")) == flow_id
        ]

        if traces:
            logger.info(f"Found {len(traces)} traces for flow_id: {flow_id}")
        else:
            logger.info(f"No traces found for flow_id: {flow_id}")

        # Sort traces by start time (newest first)
        traces.sort(key=lambda t: t.get("start_time", ""), reverse=True)
        return traces

    def add_flow_method_execution(
        self, flow_id: str, method_name: str, status: str, **kwargs
    ):
        """Add a flow method execution event to the trace.

        Args:
            flow_id: The ID of the flow
            method_name: The name of the method being executed
            status: The status of the method execution (started, completed, failed)
            **kwargs: Additional data to include in the event
        """
        # Ensure flow_id is a string
        flow_id = str(flow_id).strip()

        # Find the trace for this flow
        trace_id = self._get_trace_id_for_flow(flow_id)
        if not trace_id:
            logger.warning(f"No trace found for flow {flow_id}")
            return

        # Create the event
        event = {
            "type": "flow.method.execution",
            "timestamp": datetime.utcnow().isoformat(),
            "flow_id": flow_id,
            "method_name": method_name,
            "status": status,
            **kwargs,
        }

        # Add to trace events
        traces_storage[trace_id]["events"].append(event)

        # Update methods tracking
        if "methods" not in traces_storage[trace_id]:
            traces_storage[trace_id]["methods"] = {}

        if method_name not in traces_storage[trace_id]["methods"]:
            traces_storage[trace_id]["methods"][method_name] = {
                "name": method_name,
                "status": "running",
                "start_time": None,
                "end_time": None,
                "events": [],
            }

        method_data = traces_storage[trace_id]["methods"][method_name]
        method_data["events"].append(event)

        if status == "started":
            method_data["status"] = "running"
            method_data["start_time"] = event["timestamp"]
        elif status in ["completed", "failed"]:
            method_data["status"] = status
            method_data["end_time"] = event["timestamp"]
            if "outputs" in kwargs:
                method_data["outputs"] = kwargs["outputs"]
            if "error" in kwargs:
                method_data["error"] = kwargs["error"]

        logger.info(
            f"Added flow method execution event for flow {flow_id}, method {method_name}"
        )

    def add_flow_step_execution(
        self, flow_id: str, step_name: str, status: str, **kwargs
    ):
        """Add a flow step execution event to the trace.

        Args:
            flow_id: The ID of the flow
            step_name: The name of the step being executed
            status: The status of the step execution (started, completed, failed)
            **kwargs: Additional data to include in the event
        """
        # Ensure flow_id is a string
        flow_id = str(flow_id).strip()

        logger.info(
            f"Adding flow step execution: flow_id={flow_id}, step={step_name}, status={status}"
        )

        # Find the trace for this flow
        trace_id = self._get_trace_id_for_flow(flow_id)
        if not trace_id:
            logger.warning(f"No trace found for flow {flow_id}")
            return

        # Create the event
        event = {
            "type": "flow.step.execution",
            "timestamp": datetime.utcnow().isoformat(),
            "flow_id": flow_id,
            "step_name": step_name,
            "status": status,
            **kwargs,
        }

        # Add to trace events
        traces_storage[trace_id]["events"].append(event)

        # Update steps tracking
        if "steps" not in traces_storage[trace_id]:
            traces_storage[trace_id]["steps"] = []

        # Find or create step entry
        step_entry = None
        for step in traces_storage[trace_id]["steps"]:
            if step.get("name") == step_name:
                step_entry = step
                break

        if not step_entry:
            step_entry = {
                "name": step_name,
                "status": "running",
                "start_time": None,
                "end_time": None,
                "events": [],
            }
            traces_storage[trace_id]["steps"].append(step_entry)

        step_entry["events"].append(event)

        if status == "started":
            step_entry["status"] = "running"
            step_entry["start_time"] = event["timestamp"]
        elif status in ["completed", "failed"]:
            step_entry["status"] = status
            step_entry["end_time"] = event["timestamp"]
            if "outputs" in kwargs:
                step_entry["outputs"] = kwargs["outputs"]
            if "error" in kwargs:
                step_entry["error"] = kwargs["error"]

        logger.info(
            f"Added flow step execution event for flow {flow_id}, step {step_name}"
        )

    def get_flow_traces(self, flow_id: str) -> List[Dict[str, Any]]:
        """Get all traces for a specific flow.

        Args:
            flow_id: The ID of the flow

        Returns:
            List of trace dictionaries for the flow
        """
        # Ensure flow_id is a string
        flow_id = str(flow_id).strip()
        normalized_flow_id = flow_id.strip().lower()

        logger.info(f"Getting traces for flow_id: {flow_id}")
        logger.info(f"Total traces in storage: {len(traces_storage)}")

        # Use entity service to resolve all possible flow IDs
        possible_flow_ids = entity_service.resolve_broadcast_ids(flow_id)
        logger.info(f"Possible flow IDs from entity service: {possible_flow_ids}")

        traces = []
        if possible_flow_ids:
            # Use entity service mappings
            for tid, tdata in traces_storage.items():
                stored_flow_id = str(tdata.get("flow_id", ""))
                if stored_flow_id in possible_flow_ids:
                    traces.append(tdata)
                    logger.info(f"Found trace with flow_id {stored_flow_id}")
        else:
            # Fallback to direct matching
            logger.info(
                f"No entity mappings found, using direct matching for: {flow_id}"
            )

            # Try exact match first
            traces = [
                trace
                for trace in traces_storage.values()
                if trace.get("flow_id") == flow_id
            ]

            # If no exact matches, try case-insensitive comparison
            if not traces:
                logger.info(
                    f"No exact matches found, trying case-insensitive comparison for: {flow_id}"
                )
                traces = [
                    trace
                    for trace in traces_storage.values()
                    if trace.get("flow_id")
                    and str(trace.get("flow_id")).strip().lower() == normalized_flow_id
                ]

            # If still no matches and flow_id looks like a simple name (e.g., "flow_0"), try to find any trace
            # that might contain this as part of the flow name
            if not traces and ("_" in flow_id or flow_id.isalnum()):
                logger.info(
                    f"No matches found, trying to match by flow name pattern: {flow_id}"
                )
                traces = [
                    trace
                    for trace in traces_storage.values()
                    if trace.get("flow_name")
                    and flow_id.lower() in str(trace.get("flow_name")).lower()
                ]

            # If we found traces by name pattern, log this information
            if traces:
                logger.info(
                    f"Found {len(traces)} traces by matching flow name pattern: {flow_id}"
                )
                # Log the actual flow IDs that were matched
                matched_ids = set(trace.get("flow_id") for trace in traces)
                logger.info(f"Matched flow IDs: {matched_ids}")

        logger.info(f"Found {len(traces)} traces for flow_id: {flow_id}")
        return traces


# Create a singleton instance
telemetry_service = CrewAITelemetry()
