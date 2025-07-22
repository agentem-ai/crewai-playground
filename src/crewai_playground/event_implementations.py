"""
Async implementation methods for the unified event listener.
This file contains the actual async event processing logic.
"""

import asyncio
import logging
import json
from datetime import datetime
from .websocket_utils import broadcast_flow_update

logger = logging.getLogger(__name__)


class EventImplementationMixin:
    """Mixin class containing async event implementation methods."""

    # =============================================================================
    # Flow Event Implementations
    # =============================================================================

    async def _handle_flow_started(self, flow_id: str, event, source=None):
        """Handle flow started event asynchronously."""
        logger.info(f"Flow started event handler for flow: {flow_id}")

        flow_name = getattr(event, "flow_name", f"Flow {flow_id}")
        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "flow_started", flow_name
        )

        # Update flow state
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

        # Broadcast flow state update
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

        # Extract result from source.state if available, otherwise from event
        result = None
        if source and hasattr(source, "state"):
            try:
                state_dict = (
                    source.state.__dict__ if hasattr(source.state, "__dict__") else {}
                )
                # Try flow-specific result fields
                if "poem" in state_dict:
                    result = state_dict["poem"]
                elif "result" in state_dict:
                    result = state_dict["result"]
                elif "output" in state_dict:
                    result = state_dict["output"]
                else:
                    # Use entire state as JSON (excluding ID)
                    filtered_state = {k: v for k, v in state_dict.items() if k != "id"}
                    if filtered_state:
                        result = json.dumps(filtered_state, indent=2)
            except Exception as e:
                logger.warning(f"Error extracting result from source.state: {e}")

        # Fallback to event.result if source extraction failed
        if result is None and hasattr(event, "result") and event.result is not None:
            result = event.result

        # Update flow state
        flow_state.update(
            {
                "status": "completed",
                "outputs": result,
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

        logger.info(f"Flow {broadcast_flow_id} finished with result: {result}")

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_method_started(self, flow_id: str, event):
        """Handle method execution started event asynchronously."""
        logger.info(
            f"Method started event handler for flow: {flow_id}, method: {event.method_name}"
        )

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "method_started"
        )

        # Add step for method execution
        step_id = f"method_{event.method_name}_{id(event)}"
        step = {
            "id": step_id,
            "name": event.method_name,
            "status": "running",
            "timestamp": asyncio.get_event_loop().time(),
        }

        flow_state["steps"].append(step)

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_method_finished(self, flow_id: str, event):
        """Handle method execution finished event asynchronously."""
        logger.info(
            f"Method finished event handler for flow: {flow_id}, method: {event.method_name}"
        )

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "method_finished"
        )

        # Find and update the corresponding step
        step_id = f"method_{event.method_name}_{id(event)}"
        for step in flow_state["steps"]:
            if step["name"] == event.method_name and step["status"] == "running":
                step["status"] = "completed"
                step["timestamp"] = asyncio.get_event_loop().time()

                # Add outputs if available
                if hasattr(event, "outputs") and event.outputs is not None:
                    if hasattr(event.outputs, "raw"):
                        step["outputs"] = event.outputs.raw
                    else:
                        step["outputs"] = str(event.outputs)
                break

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_method_failed(self, flow_id: str, event):
        """Handle method execution failed event asynchronously."""
        logger.info(
            f"Method failed event handler for flow: {flow_id}, method: {event.method_name}"
        )

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "method_failed"
        )

        # Find and update the corresponding step
        for step in flow_state["steps"]:
            if step["name"] == event.method_name and step["status"] == "running":
                step["status"] = "failed"
                step["timestamp"] = asyncio.get_event_loop().time()

                # Add error if available
                if hasattr(event, "error") and event.error is not None:
                    step["error"] = str(event.error)
                break

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    # =============================================================================
    # Crew Event Implementations (Flow Context)
    # =============================================================================

    async def _handle_crew_kickoff_started_flow(self, flow_id: str, event):
        """Handle crew kickoff started event in flow context."""
        logger.info(f"Crew kickoff started (flow context) for flow: {flow_id}")

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "crew_kickoff_started"
        )

        # Add step for crew kickoff
        step_id = f"crew_kickoff_{id(event)}"
        step = {
            "id": step_id,
            "name": "Crew Kickoff",
            "status": "running",
            "timestamp": asyncio.get_event_loop().time(),
        }

        flow_state["steps"].append(step)

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_kickoff_completed_flow(self, flow_id: str, event):
        """Handle crew kickoff completed event in flow context."""
        logger.info(f"Crew kickoff completed (flow context) for flow: {flow_id}")

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "crew_kickoff_completed"
        )

        # Find and update the crew kickoff step
        for step in flow_state["steps"]:
            if step["name"] == "Crew Kickoff" and step["status"] == "running":
                step["status"] = "completed"
                step["timestamp"] = asyncio.get_event_loop().time()

                # Add result if available
                if hasattr(event, "result") and event.result is not None:
                    if hasattr(event.result, "raw"):
                        step["outputs"] = event.result.raw
                    else:
                        step["outputs"] = str(event.result)
                break

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    async def _handle_crew_kickoff_failed_flow(self, flow_id: str, event):
        """Handle crew kickoff failed event in flow context."""
        logger.info(f"Crew kickoff failed (flow context) for flow: {flow_id}")

        broadcast_flow_id, flow_state = self._ensure_flow_state_exists(
            flow_id, "crew_kickoff_failed"
        )

        # Find and update the crew kickoff step
        for step in flow_state["steps"]:
            if step["name"] == "Crew Kickoff" and step["status"] == "running":
                step["status"] = "failed"
                step["timestamp"] = asyncio.get_event_loop().time()

                # Add error if available
                if hasattr(event, "error") and event.error is not None:
                    step["error"] = str(event.error)
                break

        # Broadcast flow state update
        await broadcast_flow_update(
            broadcast_flow_id, {"type": "flow_state", "payload": flow_state}
        )

    # =============================================================================
    # Crew Event Implementations (Crew Context)
    # =============================================================================

    async def _handle_crew_kickoff_started_crew(self, execution_id: str, event):
        """Handle crew kickoff started event in crew context."""
        logger.info(
            f"Crew kickoff started (crew context) for execution: {execution_id}"
        )

        # Initialize crew state
        self.crew_state = {
            "id": execution_id,
            "name": getattr(event, "crew_name", f"Crew {execution_id}"),
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Clear previous agent and task states
        self.agent_states.clear()
        self.task_states.clear()

        # Broadcast crew state update
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

            # Add result if available
            if hasattr(event, "result") and event.result is not None:
                if hasattr(event.result, "raw"):
                    self.crew_state["result"] = event.result.raw
                else:
                    self.crew_state["result"] = str(event.result)

            # Broadcast crew state update
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

            # Add error if available
            if hasattr(event, "error") and event.error is not None:
                self.crew_state["error"] = str(event.error)

            # Broadcast crew state update
            await self.broadcast_update()

    # =============================================================================
    # Agent Event Implementations (Crew Context)
    # =============================================================================

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

        # Broadcast crew state update
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

            # Add result if available
            if hasattr(event, "result") and event.result is not None:
                self.agent_states[agent_id]["result"] = str(event.result)

            # Broadcast crew state update
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

            # Add error if available
            if hasattr(event, "error") and event.error is not None:
                self.agent_states[agent_id]["error"] = str(event.error)

            # Broadcast crew state update
            await self.broadcast_update()

    # =============================================================================
    # Task Event Implementations
    # =============================================================================

    async def _handle_task_started(self, execution_id: str, event):
        """Handle task started event."""
        logger.info(f"Task started for execution: {execution_id}")

        task_id = getattr(event, "task_id", f"task_{id(event)}")
        task_description = getattr(event, "task_description", f"Task {task_id}")

        self.task_states[task_id] = {
            "id": task_id,
            "description": task_description,
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Broadcast crew state update
        await self.broadcast_update()

    async def _handle_task_completed(self, execution_id: str, event):
        """Handle task completed event."""
        logger.info(f"Task completed for execution: {execution_id}")

        task_id = getattr(event, "task_id", f"task_{id(event)}")

        if task_id in self.task_states:
            self.task_states[task_id].update(
                {
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            # Add result if available
            if hasattr(event, "result") and event.result is not None:
                self.task_states[task_id]["result"] = str(event.result)

            # Broadcast crew state update
            await self.broadcast_update()

    # =============================================================================
    # Stub implementations for other events (to avoid missing method errors)
    # =============================================================================

    async def _handle_agent_execution_started_flow(self, flow_id: str, event):
        """Handle agent execution started event in flow context."""
        logger.debug(f"Agent execution started (flow context) for flow: {flow_id}")
        # Add to flow steps if needed

    async def _handle_agent_execution_completed_flow(self, flow_id: str, event):
        """Handle agent execution completed event in flow context."""
        logger.debug(f"Agent execution completed (flow context) for flow: {flow_id}")
        # Update flow steps if needed

    async def _handle_agent_execution_error_flow(self, flow_id: str, event):
        """Handle agent execution error event in flow context."""
        logger.debug(f"Agent execution error (flow context) for flow: {flow_id}")
        # Update flow steps if needed

    # Tool event stubs
    async def _handle_tool_usage_started_flow(self, flow_id: str, event):
        logger.debug(f"Tool usage started (flow context) for flow: {flow_id}")

    async def _handle_tool_usage_finished_flow(self, flow_id: str, event):
        logger.debug(f"Tool usage finished (flow context) for flow: {flow_id}")

    async def _handle_tool_usage_error_flow(self, flow_id: str, event):
        logger.debug(f"Tool usage error (flow context) for flow: {flow_id}")

    async def _handle_tool_validate_input_error_flow(self, flow_id: str, event):
        logger.debug(f"Tool validate input error (flow context) for flow: {flow_id}")

    async def _handle_tool_execution_error_flow(self, flow_id: str, event):
        logger.debug(f"Tool execution error (flow context) for flow: {flow_id}")

    async def _handle_tool_selection_error_flow(self, flow_id: str, event):
        logger.debug(f"Tool selection error (flow context) for flow: {flow_id}")

    # Tool event stubs (crew context)
    async def _handle_tool_usage_started_crew(self, execution_id: str, event):
        logger.debug(f"Tool usage started (crew context) for execution: {execution_id}")

    async def _handle_tool_usage_finished_crew(self, execution_id: str, event):
        logger.debug(
            f"Tool usage finished (crew context) for execution: {execution_id}"
        )

    async def _handle_tool_usage_error_crew(self, execution_id: str, event):
        logger.debug(f"Tool usage error (crew context) for execution: {execution_id}")

    async def _handle_tool_validate_input_error_crew(self, execution_id: str, event):
        logger.debug(
            f"Tool validate input error (crew context) for execution: {execution_id}"
        )

    async def _handle_tool_execution_error_crew(self, execution_id: str, event):
        logger.debug(
            f"Tool execution error (crew context) for execution: {execution_id}"
        )

    async def _handle_tool_selection_error_crew(self, execution_id: str, event):
        logger.debug(
            f"Tool selection error (crew context) for execution: {execution_id}"
        )

    # LLM event stubs
    async def _handle_llm_call_started_flow(self, flow_id: str, event):
        logger.debug(f"LLM call started (flow context) for flow: {flow_id}")

    async def _handle_llm_call_completed_flow(self, flow_id: str, event):
        logger.debug(f"LLM call completed (flow context) for flow: {flow_id}")

    async def _handle_llm_call_failed_flow(self, flow_id: str, event):
        logger.debug(f"LLM call failed (flow context) for flow: {flow_id}")

    async def _handle_llm_stream_chunk_flow(self, flow_id: str, event):
        logger.debug(f"LLM stream chunk (flow context) for flow: {flow_id}")

    async def _handle_llm_call_started_crew(self, execution_id: str, event):
        logger.debug(f"LLM call started (crew context) for execution: {execution_id}")

    async def _handle_llm_call_completed_crew(self, execution_id: str, event):
        logger.debug(f"LLM call completed (crew context) for execution: {execution_id}")

    async def _handle_llm_call_failed_crew(self, execution_id: str, event):
        logger.debug(f"LLM call failed (crew context) for execution: {execution_id}")

    async def _handle_llm_stream_chunk_crew(self, execution_id: str, event):
        logger.debug(f"LLM stream chunk (crew context) for execution: {execution_id}")

    # Custom event stubs
    async def _handle_crew_initialization_requested(self, execution_id: str, event):
        logger.debug(f"Crew initialization requested for execution: {execution_id}")

    async def _handle_crew_initialization_completed(self, execution_id: str, event):
        logger.debug(f"Crew initialization completed for execution: {execution_id}")

    # Additional crew event stubs
    async def _handle_crew_test_started(self, execution_id: str, event):
        logger.debug(f"Crew test started for execution: {execution_id}")

    async def _handle_crew_test_completed(self, execution_id: str, event):
        logger.debug(f"Crew test completed for execution: {execution_id}")

    async def _handle_crew_test_failed(self, execution_id: str, event):
        logger.debug(f"Crew test failed for execution: {execution_id}")

    async def _handle_crew_train_started(self, execution_id: str, event):
        logger.debug(f"Crew train started for execution: {execution_id}")

    async def _handle_crew_train_completed(self, execution_id: str, event):
        logger.debug(f"Crew train completed for execution: {execution_id}")

    async def _handle_crew_train_failed(self, execution_id: str, event):
        logger.debug(f"Crew train failed for execution: {execution_id}")
