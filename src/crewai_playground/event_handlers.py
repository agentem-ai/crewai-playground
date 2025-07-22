"""
Event handler implementations for the unified event listener.
This file contains the actual event handling logic to keep the main file manageable.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class EventHandlerMixin:
    """Mixin class containing event handler implementations."""

    # =============================================================================
    # Utility Methods
    # =============================================================================

    def _schedule(self, coro):
        """Schedule coroutine safely on an event loop."""
        if self.loop and self.loop.is_running():
            asyncio.create_task(coro)
        else:
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(coro)
            except RuntimeError:
                logger.warning(
                    "No running event loop found, cannot schedule async task"
                )

    def _extract_execution_id(self, source, event) -> Optional[str]:
        """Extract execution ID from source or event, handling both flow and crew contexts."""
        # Try to get flow ID first (for flow events)
        if hasattr(source, "id") and source.id:
            return str(source.id)

        # Try to get crew ID (for crew events)
        if hasattr(event, "crew_id") and event.crew_id:
            return str(event.crew_id)

        # Try to get from source attributes
        if hasattr(source, "crew_id") and source.crew_id:
            return str(source.crew_id)

        # Fallback to source string representation
        if source:
            return str(source)

        return None

    def _is_flow_context(self, source, event) -> bool:
        """Determine if this event is in a flow context."""
        # Check if source is a flow object
        if hasattr(source, "__class__") and "Flow" in source.__class__.__name__:
            return True

        # Check if we have flow-specific attributes
        if hasattr(source, "state") and hasattr(source, "id"):
            return True

        return False

    def _ensure_flow_state_exists(
        self, flow_id: str, event_name: str, flow_name: str = None
    ):
        """Ensure flow state exists for the given flow ID."""
        # Check if this is an internal flow ID that needs to be mapped to an API flow ID
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

    def get_flow_state(self, flow_id: str):
        """Get the current state of a flow."""
        return self.flow_states.get(flow_id)

    # =============================================================================
    # Flow Event Handlers
    # =============================================================================

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

    # =============================================================================
    # Crew Event Handlers
    # =============================================================================

    def handle_crew_kickoff_started(self, source, event):
        """Handle crew kickoff started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_crew_kickoff_started_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_crew_kickoff_started_crew(execution_id, event)
                )

    def handle_crew_kickoff_completed(self, source, event):
        """Handle crew kickoff completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_crew_kickoff_completed_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_crew_kickoff_completed_crew(execution_id, event)
                )

    def handle_crew_kickoff_failed(self, source, event):
        """Handle crew kickoff failed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_crew_kickoff_failed_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_crew_kickoff_failed_crew(execution_id, event)
                )

    # =============================================================================
    # Agent Event Handlers
    # =============================================================================

    def handle_agent_execution_started(self, source, event):
        """Handle agent execution started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_agent_execution_started_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_agent_execution_started_crew(execution_id, event)
                )

    def handle_agent_execution_completed(self, source, event):
        """Handle agent execution completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_agent_execution_completed_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_agent_execution_completed_crew(execution_id, event)
                )

    def handle_agent_execution_error(self, source, event):
        """Handle agent execution error event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_agent_execution_error_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_agent_execution_error_crew(execution_id, event)
                )

    # =============================================================================
    # Task Event Handlers
    # =============================================================================

    def handle_task_started(self, source, event):
        """Handle task started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(self._handle_task_started(execution_id, event))

    def handle_task_completed(self, source, event):
        """Handle task completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(self._handle_task_completed(execution_id, event))

    # =============================================================================
    # Tool Event Handlers
    # =============================================================================

    def handle_tool_usage_started(self, source, event):
        """Handle tool usage started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_tool_usage_started_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_tool_usage_started_crew(execution_id, event)
                )

    def handle_tool_usage_finished(self, source, event):
        """Handle tool usage finished event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_tool_usage_finished_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_tool_usage_finished_crew(execution_id, event)
                )

    def handle_tool_usage_error(self, source, event):
        """Handle tool usage error event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(self._handle_tool_usage_error_flow(execution_id, event))
            else:
                self._schedule(self._handle_tool_usage_error_crew(execution_id, event))

    def handle_tool_validate_input_error(self, source, event):
        """Handle tool validate input error event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_tool_validate_input_error_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_tool_validate_input_error_crew(execution_id, event)
                )

    def handle_tool_execution_error(self, source, event):
        """Handle tool execution error event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_tool_execution_error_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_tool_execution_error_crew(execution_id, event)
                )

    def handle_tool_selection_error(self, source, event):
        """Handle tool selection error event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_tool_selection_error_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_tool_selection_error_crew(execution_id, event)
                )

    # =============================================================================
    # LLM Event Handlers
    # =============================================================================

    def handle_llm_call_started(self, source, event):
        """Handle LLM call started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(self._handle_llm_call_started_flow(execution_id, event))
            else:
                self._schedule(self._handle_llm_call_started_crew(execution_id, event))

    def handle_llm_call_completed(self, source, event):
        """Handle LLM call completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(
                    self._handle_llm_call_completed_flow(execution_id, event)
                )
            else:
                self._schedule(
                    self._handle_llm_call_completed_crew(execution_id, event)
                )

    def handle_llm_call_failed(self, source, event):
        """Handle LLM call failed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(self._handle_llm_call_failed_flow(execution_id, event))
            else:
                self._schedule(self._handle_llm_call_failed_crew(execution_id, event))

    def handle_llm_stream_chunk(self, source, event):
        """Handle LLM stream chunk event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            if self._is_flow_context(source, event):
                self._schedule(self._handle_llm_stream_chunk_flow(execution_id, event))
            else:
                self._schedule(self._handle_llm_stream_chunk_crew(execution_id, event))

    # =============================================================================
    # Custom Event Handlers
    # =============================================================================

    def handle_crew_initialization_requested(self, source, event):
        """Handle crew initialization requested event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(
                self._handle_crew_initialization_requested(execution_id, event)
            )

    def handle_crew_initialization_completed(self, source, event):
        """Handle crew initialization completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(
                self._handle_crew_initialization_completed(execution_id, event)
            )

    # Additional handlers for missing events
    def handle_crew_test_started(self, source, event):
        """Handle crew test started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(self._handle_crew_test_started(execution_id, event))

    def handle_crew_test_completed(self, source, event):
        """Handle crew test completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(self._handle_crew_test_completed(execution_id, event))

    def handle_crew_test_failed(self, source, event):
        """Handle crew test failed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(self._handle_crew_test_failed(execution_id, event))

    def handle_crew_train_started(self, source, event):
        """Handle crew train started event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(self._handle_crew_train_started(execution_id, event))

    def handle_crew_train_completed(self, source, event):
        """Handle crew train completed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(self._handle_crew_train_completed(execution_id, event))

    def handle_crew_train_failed(self, source, event):
        """Handle crew train failed event."""
        execution_id = self._extract_execution_id(source, event)
        if execution_id:
            self._schedule(self._handle_crew_train_failed(execution_id, event))
