# CrewAI Visualization Architecture

## Overview

The CrewAI visualization system provides real-time monitoring and visualization of crew and flow executions. It's built on a WebSocket-based event system that captures execution events and broadcasts them to connected clients for visualization.

## Architecture Components

### 1. Backend (Python)

#### 1.1 Event System
- **CrewAI Event Bus**: Global event bus (`crewai_event_bus`) for publishing and subscribing to events
- **Event Listeners**:
  - `CrewVisualizationListener`: Handles crew execution events
  - `FlowWebSocketEventListener`: Manages flow execution events

#### 1.2 WebSocket Endpoints
- `/ws/crew-visualization`: For crew execution visualization
- `/ws/flow/{flow_id}`: For flow execution visualization

#### 1.3 Core Components

##### CrewVisualizationListener
- Maintains state of crew executions
- Tracks agents, tasks, and their statuses
- Broadcasts updates to connected WebSocket clients

##### FlowWebSocketEventListener
- Manages flow execution states
- Handles flow-specific events and state transitions
- Broadcasts flow updates to connected clients

### 2. Frontend (React/TypeScript)

#### 2.1 Core Components
- **CrewAgentCanvas**: Main visualization component for crew execution
- **FlowCanvas**: Visualization component for flow execution
- **TraceTimeline**: Displays execution traces and timing information

#### 2.2 State Management
- Uses React hooks for local component state
- Global state management via custom hooks and context
- Real-time updates via WebSocket connections

## Data Flow

1. **Event Generation**
   - Crew/flow execution triggers events in CrewAI
   - Events are published to the global event bus

2. **Event Processing**
   - Event listeners process relevant events
   - State is updated based on event data
   - Updates are queued for broadcasting

3. **WebSocket Communication**
   - Frontend establishes WebSocket connection
   - Backend broadcasts state updates to all connected clients
   - Frontend updates UI based on received data

## Telemetry Integration

### Event Types Tracked
- Crew execution start/complete
- Agent task start/complete
- Flow start/complete
- Method execution start/complete
- Error events

### Data Captured
- Timestamps
- Execution context (crew ID, flow ID, etc.)
- Performance metrics
- Inputs/outputs
- Error details

## Implementation Details

### Backend Event Handling
```python
# Example event handler in CrewVisualizationListener
@crewai_event_bus.on(CrewKickoffStartedEvent)
def on_crew_kickoff_started(source, event):
    # Update crew state
    self.crew_state = {
        "id": crew_id,
        "name": event.crew_name,
        "status": "running",
        "started_at": datetime.utcnow().isoformat()
    }
    # Broadcast update
    asyncio.create_task(self.broadcast_update())
```

### Frontend WebSocket Connection
```typescript
// In CrewAgentCanvas.tsx
useEffect(() => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws/crew-visualization`);
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    setState(prevState => ({
      ...prevState,
      ...data
    }));
  };
  
  return () => ws.close();
}, [crewId]);
```

## Error Handling

### Connection Management
- Automatic reconnection on connection loss
- Connection timeouts with exponential backoff
- Graceful degradation when WebSocket is unavailable

### Error Recovery
- State reconciliation on reconnection
- Error boundaries in React components
- User-friendly error messages

## Performance Considerations

### Backend
- Efficient state management to minimize memory usage
- Batch updates where possible
- Asynchronous event processing

### Frontend
- Virtualized rendering for large datasets
- Memoization to prevent unnecessary re-renders
- Efficient diffing of state updates

## Security Considerations

- WebSocket connections use WSS in production
- Input validation on both client and server
- Rate limiting on WebSocket connections
- Authentication/authorization for sensitive operations

## Monitoring and Debugging

### Logging
- Detailed logging of WebSocket events
- Error tracking and reporting
- Performance metrics collection

### Debug Tools
- Browser developer tools
- WebSocket message inspection
- State visualization in UI

## Future Improvements

1. **Enhanced Visualization**
   - More detailed execution graphs
   - Custom visualization plugins
   - 3D visualization options

2. **Performance Optimizations**
   - WebSocket message compression
   - Delta updates instead of full state
   - Client-side caching

3. **Advanced Features**
   - Time travel debugging
   - Execution replay
   - Automated testing integration

## Dependencies

### Backend
- FastAPI for WebSocket support
- Pydantic for data validation
- asyncio for async operations

### Frontend
- React for UI components
- ReactFlow for graph visualization
- WebSocket API for real-time updates

## Conclusion

The CrewAI visualization system provides a robust, real-time view into crew and flow executions. Its modular design allows for easy extension and customization while maintaining good performance characteristics even under heavy load.
