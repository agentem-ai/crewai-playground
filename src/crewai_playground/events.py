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
