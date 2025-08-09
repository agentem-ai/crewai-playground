from typing import Dict, List, Any, Optional
from datetime import datetime
from crewai.utilities.events.base_events import BaseEvent


class CrewInitializationRequestedEvent(BaseEvent):
    """Event emitted when a crew initialization is requested."""
    type: str = "crew_initialization_requested"
    crew_id: str
    crew_name: str
    timestamp: datetime = None


class CrewInitializationCompletedEvent(BaseEvent):
    """Event emitted when crew initialization is completed."""
    type: str = "crew_initialization_completed"
    crew_id: str
    crew_name: str
    agents: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]]
    timestamp: datetime = None


class FlowInitializationRequestedEvent(BaseEvent):
    """Event emitted when a flow initialization is requested."""
    type: str = "flow_initialization_requested"
    flow_id: str
    internal_flow_id: str
    flow_name: str
    timestamp: datetime = None


class FlowInitializationCompletedEvent(BaseEvent):
    """Event emitted when flow initialization is completed."""
    type: str = "flow_initialization_completed"
    flow_id: str
    internal_flow_id: str
    flow_name: str
    methods: List[Dict[str, Any]]
    structure: Dict[str, Any]
    timestamp: datetime = None
