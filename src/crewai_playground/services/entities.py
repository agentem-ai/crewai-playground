"""
Entity Service for managing crew and flow ID mappings throughout the application.

This service provides a centralized way to:
- Map between API IDs and internal CrewAI-generated IDs
- Track entity relationships and aliases
- Provide consistent ID resolution across components
"""

import logging
from typing import Dict, List, Optional, Set, Union
from dataclasses import dataclass, field
from threading import Lock
import uuid

logger = logging.getLogger(__name__)


@dataclass
class EntityMapping:
    """Represents a mapping between different ID formats for an entity."""
    primary_id: str  # The main ID used by the API
    internal_id: Optional[str] = None  # CrewAI-generated internal ID
    aliases: Set[str] = field(default_factory=set)  # Alternative IDs/names
    entity_type: str = "crew"  # "crew" or "flow"
    name: Optional[str] = None  # Human-readable name
    
    def __post_init__(self):
        """Ensure aliases is a set and includes the primary_id."""
        if not isinstance(self.aliases, set):
            self.aliases = set(self.aliases) if self.aliases else set()
        self.aliases.add(self.primary_id)
        if self.internal_id:
            self.aliases.add(self.internal_id)
        if self.name:
            self.aliases.add(self.name)


class EntityService:
    """Centralized service for managing entity ID mappings."""
    
    def __init__(self):
        self._mappings: Dict[str, EntityMapping] = {}
        self._lock = Lock()
        
    def register_entity(
        self, 
        primary_id: str, 
        internal_id: Optional[str] = None,
        entity_type: str = "crew",
        name: Optional[str] = None,
        aliases: Optional[List[str]] = None
    ) -> EntityMapping:
        """
        Register a new entity or update an existing one.
        
        Args:
            primary_id: The main ID used by the API
            internal_id: CrewAI-generated internal ID (if different)
            entity_type: Type of entity ("crew" or "flow")
            name: Human-readable name
            aliases: Additional aliases for this entity
            
        Returns:
            The EntityMapping object
        """
        with self._lock:
            # Check if we already have this entity registered
            existing = self._find_existing_mapping(primary_id, internal_id)
            
            if existing:
                # Update existing mapping
                if internal_id and internal_id != existing.internal_id:
                    existing.internal_id = internal_id
                    existing.aliases.add(internal_id)
                if name and name != existing.name:
                    existing.name = name
                    existing.aliases.add(name)
                if aliases:
                    existing.aliases.update(aliases)
                
                logger.debug(f"Updated entity mapping for {primary_id}: {existing}")
                return existing
            else:
                # Create new mapping
                alias_set = set(aliases) if aliases else set()
                mapping = EntityMapping(
                    primary_id=primary_id,
                    internal_id=internal_id,
                    entity_type=entity_type,
                    name=name,
                    aliases=alias_set
                )
                
                # Store mapping under all known IDs for fast lookup
                self._mappings[primary_id] = mapping
                if internal_id:
                    self._mappings[internal_id] = mapping
                for alias in mapping.aliases:
                    self._mappings[alias] = mapping
                
                logger.debug(f"Registered new entity mapping: {mapping}")
                return mapping
    
    def _find_existing_mapping(self, primary_id: str, internal_id: Optional[str] = None) -> Optional[EntityMapping]:
        """Find existing mapping by primary_id or internal_id."""
        # Check primary_id first
        if primary_id in self._mappings:
            return self._mappings[primary_id]
        
        # Check internal_id
        if internal_id and internal_id in self._mappings:
            return self._mappings[internal_id]
        
        return None
    
    def get_mapping(self, entity_id: str) -> Optional[EntityMapping]:
        """Get the mapping for an entity by any of its known IDs."""
        with self._lock:
            return self._mappings.get(entity_id)
    
    def get_primary_id(self, entity_id: str) -> Optional[str]:
        """Get the primary ID for an entity by any of its known IDs."""
        mapping = self.get_mapping(entity_id)
        return mapping.primary_id if mapping else None
    
    def get_internal_id(self, entity_id: str) -> Optional[str]:
        """Get the internal ID for an entity by any of its known IDs."""
        mapping = self.get_mapping(entity_id)
        return mapping.internal_id if mapping else None
    
    def get_all_ids(self, entity_id: str) -> List[str]:
        """Get all known IDs/aliases for an entity."""
        mapping = self.get_mapping(entity_id)
        return list(mapping.aliases) if mapping else []
    
    def resolve_broadcast_ids(self, entity_id: str) -> List[str]:
        """
        Get all IDs that should be used for broadcasting/matching.
        
        This includes:
        - Primary ID
        - Internal ID
        - All aliases
        - String versions of IDs
        - Special crew_X formats for development
        """
        mapping = self.get_mapping(entity_id)
        if not mapping:
            return [entity_id, str(entity_id)]
        
        broadcast_ids = list(mapping.aliases)
        
        # Add string versions
        for id_val in list(broadcast_ids):
            broadcast_ids.append(str(id_val))
        
        # Add crew_X formats for development (if this looks like a UUID)
        if mapping.entity_type == "crew" and len(str(mapping.primary_id)) > 30:
            for i in range(10):  # crew_0 through crew_9
                broadcast_ids.append(f"crew_{i}")
        
        # Remove duplicates while preserving order
        unique_ids = []
        for id_val in broadcast_ids:
            if id_val not in unique_ids:
                unique_ids.append(id_val)
        
        return unique_ids
    
    def should_broadcast_to_client(self, entity_id: str, client_crew_id: Optional[str]) -> bool:
        """
        Determine if an update should be broadcast to a client based on their crew filter.
        
        Args:
            entity_id: The entity ID from the update
            client_crew_id: The crew ID the client is filtered to
            
        Returns:
            True if the update should be sent to the client
        """
        # No client filter or no entity - send to all
        if not client_crew_id or not entity_id:
            return True
        
        # Get all possible IDs for this entity
        broadcast_ids = self.resolve_broadcast_ids(entity_id)
        
        # Check if client's crew ID matches any of our broadcast IDs
        if client_crew_id in broadcast_ids:
            return True
        
        # Special case for crew_X format during development
        if client_crew_id.startswith("crew_"):
            return True
        
        return False
    
    def add_alias(self, entity_id: str, alias: str) -> bool:
        """Add an alias to an existing entity."""
        with self._lock:
            mapping = self.get_mapping(entity_id)
            if mapping:
                mapping.aliases.add(alias)
                self._mappings[alias] = mapping
                logger.debug(f"Added alias '{alias}' to entity {entity_id}")
                return True
            return False
    
    def get_entities_by_type(self, entity_type: str) -> List[EntityMapping]:
        """Get all entities of a specific type."""
        with self._lock:
            seen = set()
            entities = []
            for mapping in self._mappings.values():
                if mapping.entity_type == entity_type and mapping.primary_id not in seen:
                    entities.append(mapping)
                    seen.add(mapping.primary_id)
            return entities
    
    def clear_entities(self, entity_type: Optional[str] = None):
        """Clear all entities or entities of a specific type."""
        with self._lock:
            if entity_type:
                # Remove entities of specific type
                to_remove = []
                for key, mapping in self._mappings.items():
                    if mapping.entity_type == entity_type:
                        to_remove.append(key)
                
                for key in to_remove:
                    del self._mappings[key]
                
                logger.debug(f"Cleared all {entity_type} entities")
            else:
                # Clear all entities
                self._mappings.clear()
                logger.debug("Cleared all entities")
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about registered entities."""
        with self._lock:
            stats = {"total_mappings": len(set(m.primary_id for m in self._mappings.values()))}
            
            # Count by type
            type_counts = {}
            seen_primary_ids = set()
            for mapping in self._mappings.values():
                if mapping.primary_id not in seen_primary_ids:
                    seen_primary_ids.add(mapping.primary_id)
                    type_counts[mapping.entity_type] = type_counts.get(mapping.entity_type, 0) + 1
            
            stats.update(type_counts)
            return stats


# Global singleton instance
entity_service = EntityService()


# Convenience functions for common operations
def register_crew(primary_id: str, internal_id: Optional[str] = None, name: Optional[str] = None) -> EntityMapping:
    """Register a crew entity."""
    return entity_service.register_entity(primary_id, internal_id, "crew", name)


def register_flow(primary_id: str, internal_id: Optional[str] = None, name: Optional[str] = None) -> EntityMapping:
    """Register a flow entity."""
    return entity_service.register_entity(primary_id, internal_id, "flow", name)


def get_primary_id(entity_id: str) -> Optional[str]:
    """Get the primary ID for any entity ID."""
    return entity_service.get_primary_id(entity_id)


def get_broadcast_ids(entity_id: str) -> List[str]:
    """Get all IDs for broadcasting/matching."""
    return entity_service.resolve_broadcast_ids(entity_id)


def should_broadcast(entity_id: str, client_crew_id: Optional[str]) -> bool:
    """Check if update should be broadcast to client."""
    return entity_service.should_broadcast_to_client(entity_id, client_crew_id)
