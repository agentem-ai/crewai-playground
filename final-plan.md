# Crew Initialization and Visualization Enhancement Plan

## Feature Overview

**Feature Name:** Enhanced Crew Initialization and Visualization

**Problem Statement:** Currently, when users change crews on the kickoff page (http://localhost:8000/kickoff), the visualization doesn't properly reinitialize. This creates inconsistencies between the selected crew and the displayed visualization.

**Solution:** Implement a seamless crew initialization and visualization system that automatically resets and initializes visualization when a user selects a different crew.

## Expected Outcomes

1. When a user selects a different crew from the dropdown, the visualization should reset completely
2. The new crew's structure (agents and tasks) should be displayed immediately upon selection
3. Visual feedback should indicate the initialization process
4. Error states should be handled gracefully with user-friendly messages
5. The system should maintain WebSocket connection efficiency
6. The initialization process should be fast and responsive

## Implementation Overview

This implementation will require changes to both frontend (React) and backend (Python/FastAPI) components. The plan is structured into four main phases:

1. **Backend Enhancements:** Modify server-side code to support crew initialization events
2. **Frontend State Management:** Implement robust state handling for crew changes
3. **Visualization Components:** Update visualization rendering for initialization states
4. **Testing & Optimization:** Ensure reliability and performance

## Detailed Implementation Plan

### Phase 1: Backend Enhancements

#### 1.1 Create Crew Initialization Event Types

Add new event types to support the initialization flow:

```python
class CrewInitializationRequestedEvent(BaseEvent):
    """Event emitted when a crew initialization is requested."""
    crew_id: str
    crew_name: str
    timestamp: datetime = None

class CrewInitializationCompletedEvent(BaseEvent):
    """Event emitted when crew initialization is completed."""
    crew_id: str
    crew_name: str
    agents: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]]
    timestamp: datetime = None
```

#### 1.2 Enhance CrewVisualizationListener

Update the `CrewVisualizationListener` class in `event_listener.py` to handle initialization events:

```python
def setup_listeners(self, crewai_event_bus):
    # Existing event handlers...
    
    @crewai_event_bus.on(CrewInitializationRequestedEvent)
    def on_crew_initialization_requested(source, event):
        """Handle crew initialization request."""
        crew_id = event.crew_id
        self.reset_state()
        self.crew_state = {
            "id": crew_id,
            "name": event.crew_name,
            "status": "initializing",
            "started_at": event.timestamp or datetime.utcnow(),
        }
        # Schedule async broadcast
        asyncio.create_task(self.broadcast_update())
        
    @crewai_event_bus.on(CrewInitializationCompletedEvent)
    def on_crew_initialization_completed(source, event):
        """Handle crew initialization completion."""
        crew_id = event.crew_id
        # Update crew state
        self.crew_state = {
            "id": crew_id,
            "name": event.crew_name,
            "status": "ready",
            "initialized_at": event.timestamp or datetime.utcnow(),
        }
        
        # Initialize agent states
        for agent in event.agents:
            agent_id = agent.get("id")
            if agent_id:
                self.agent_states[agent_id] = agent
        
        # Initialize task states
        for task in event.tasks:
            task_id = task.get("id")
            if task_id:
                self.task_states[task_id] = task
                
        # Schedule async broadcast
        asyncio.create_task(self.broadcast_update())
```

#### 1.3 Modify WebSocket Connection Management

Enhance the WebSocket connection to handle crew-specific registrations in `server.py`:

```python
@app.websocket("/ws/crew-visualization/{crew_id}")
async def websocket_endpoint(websocket: WebSocket, crew_id: str = None):
    """WebSocket endpoint with optional crew_id path parameter."""
    client_id = str(uuid.uuid4())
    await crew_visualization_listener.connect(websocket, client_id, crew_id)
    
    try:
        # Send confirmation message
        await websocket.send_json({
            "type": "connection_established",
            "client_id": client_id,
            "crew_id": crew_id
        })
        
        # Process incoming messages
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type", "")
                
                # Handle crew registration message
                if msg_type == "register_crew":
                    new_crew_id = message.get("crew_id")
                    if new_crew_id:
                        await crew_visualization_listener.register_client_for_crew(
                            client_id, new_crew_id
                        )
                        await websocket.send_json({
                            "type": "crew_registered",
                            "crew_id": new_crew_id
                        })
                
                # Handle state request message
                elif msg_type == "request_state":
                    await crew_visualization_listener.send_state_to_client(client_id)
                    
            except json.JSONDecodeError:
                logging.error(f"Invalid JSON message: {data}")
                
    except WebSocketDisconnect:
        crew_visualization_listener.disconnect(client_id)
        logging.info(f"Client {client_id} disconnected")
    except Exception as e:
        logging.error(f"Error in WebSocket connection: {str(e)}")
        crew_visualization_listener.disconnect(client_id)
```

#### 1.4 Add Crew Initialization API Endpoint

Create a new API endpoint to trigger crew initialization:

```python
@app.post("/api/crews/{crew_id}/initialize")
async def initialize_crew(crew_id: str) -> JSONResponse:
    """Initialize a specific crew structure without running it.
    
    Args:
        crew_id: The ID of the crew to initialize
        
    Returns:
        JSONResponse with initialization status
    """
    try:
        # Find the crew path
        crew_path = None
        for crew in discovered_crews:
            if crew.get("id") == crew_id:
                crew_path = crew.get("path")
                break
                
        if not crew_path:
            raise HTTPException(
                status_code=404,
                detail=f"Crew with ID {crew_id} not found"
            )
            
        # Load the crew
        crew_instance, crew_name = load_crew_from_module(Path(crew_path))
        
        # Get event bus and set up visualization listener
        if hasattr(crew_instance, "get_event_bus"):
            event_bus = crew_instance.get_event_bus()
        else:
            from crewai.utilities.events import crewai_event_bus
            event_bus = crewai_event_bus
            
        # Ensure listener is setup
        crew_visualization_listener.setup_listeners(event_bus)
        
        # Extract agents and tasks info
        agents = []
        for agent in crew_instance.agents:
            agent_id = str(agent.id) if hasattr(agent, "id") else f"agent_{len(agents)}"
            agents.append({
                "id": agent_id,
                "role": agent.role,
                "name": agent.name,
                "status": "waiting",
                "description": agent.goal
            })
            
        # Extract tasks info
        tasks = []
        task_map = {}
        for task in crew_instance.tasks:
            task_id = str(task.id) if hasattr(task, "id") else f"task_{len(tasks)}"
            task_map[task_id] = task
            tasks.append({
                "id": task_id,
                "description": task.description,
                "status": "pending",
                "agent_id": str(task.agent.id) if task.agent and hasattr(task.agent, "id") else None
            })
            
        # Emit initialization events
        event_bus.emit(
            crew_instance,
            CrewInitializationRequestedEvent(
                crew_id=crew_id, 
                crew_name=crew_name,
                timestamp=datetime.utcnow()
            )
        )
        
        # After extracting structure, emit completion event
        event_bus.emit(
            crew_instance,
            CrewInitializationCompletedEvent(
                crew_id=crew_id,
                crew_name=crew_name,
                agents=agents,
                tasks=tasks,
                timestamp=datetime.utcnow()
            )
        )
        
        return JSONResponse(
            content={
                "status": "success",
                "message": f"Crew {crew_name} initialized",
                "crew_id": crew_id,
                "agent_count": len(agents),
                "task_count": len(tasks)
            },
            status_code=200
        )
        
    except Exception as e:
        logging.error(f"Error initializing crew {crew_id}: {str(e)}")
        return JSONResponse(
            content={
                "status": "error",
                "message": f"Error initializing crew: {str(e)}"
            },
            status_code=500
        )
```

### Phase 2: Frontend State Management

#### 2.1 Enhanced Client Management in CrewVisualizationListener

Update the `CrewVisualizationListener` class to handle client registration and crew-specific updates:

```python
class CrewVisualizationListener(BaseEventListener):
    def __init__(self):
        self._registered_buses = set()
        super().__init__()
        # Replace simple connection list with client dictionary
        self.clients = {}  # client_id -> {websocket, crew_id, connected_at, last_ping}
        self.crew_state = {}
        self.agent_states = {}
        self.task_states = {}
    
    async def connect(self, websocket: WebSocket, client_id: str, crew_id: str = None):
        """Connect a new WebSocket client."""
        await websocket.accept()
        self.clients[client_id] = {
            "websocket": websocket,
            "crew_id": crew_id,
            "connected_at": datetime.utcnow(),
            "last_ping": datetime.utcnow()
        }
        
        # If crew_id provided, send current state for that crew
        if crew_id and crew_id in self.crew_state:
            await self.send_state_to_client(client_id)
    
    def disconnect(self, client_id: str):
        """Disconnect a client by ID."""
        if client_id in self.clients:
            del self.clients[client_id]
    
    async def register_client_for_crew(self, client_id: str, crew_id: str):
        """Register a client for updates from a specific crew."""
        if client_id in self.clients:
            self.clients[client_id]["crew_id"] = crew_id
            await self.send_state_to_client(client_id)
    
    async def send_state_to_client(self, client_id: str):
        """Send current state to a specific client."""
        if client_id not in self.clients:
            return
            
        client = self.clients[client_id]
        websocket = client["websocket"]
        crew_id = client["crew_id"]
        
        # Only send state for the client's registered crew
        if crew_id and self.crew_state and self.crew_state.get("id") == crew_id:
            try:
                state = {
                    "crew": self.crew_state,
                    "agents": list(self.agent_states.values()),
                    "tasks": list(self.task_states.values())
                }
                await websocket.send_json(state, encoder=CustomJSONEncoder)
            except Exception as e:
                logging.error(f"Error sending state to client {client_id}: {str(e)}")
                self.disconnect(client_id)
    
    async def broadcast_update(self):
        """Broadcast current state to all connected clients."""
        for client_id, client in list(self.clients.items()):
            crew_id = client.get("crew_id")
            # Only broadcast to clients registered for this crew
            if not crew_id or (self.crew_state and self.crew_state.get("id") == crew_id):
                try:
                    websocket = client["websocket"]
                    state = {
                        "crew": self.crew_state,
                        "agents": list(self.agent_states.values()),
                        "tasks": list(self.task_states.values()),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    await websocket.send_json(state, encoder=CustomJSONEncoder)
                except Exception as e:
                    logging.error(f"Error broadcasting to client {client_id}: {str(e)}")
                    self.disconnect(client_id)
```

#### 2.2 Update CrewAgentCanvas Component

Modify the React component to handle crew initialization:

```typescript
// In CrewAgentCanvas.tsx
const CrewAgentCanvas: React.FC<CrewAgentCanvasProps> = ({ 
  crewId, 
  isRunning, 
  resetKey = 0 
}) => {
  const wsRef = useRef<WebSocket | null>(null);
  const clientIdRef = useRef<string | null>(null);
  const [state, setState] = useState<VisualizationState>({ 
    crew: null, agents: [], tasks: [] 
  });
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const maxRetries = 5;
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  
  // Initialize WebSocket connection
  useEffect(() => {
    // Close any existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }
    
    // Reset states
    setState({ crew: null, agents: [], tasks: [] });
    setNodes([]);
    setEdges([]);
    setError(null);
    
    // Connection URL with protocol detection
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(
      `${protocol}//${window.location.host}/ws/crew-visualization/${crewId || ''}`
    );
    
    // Connection opened
    ws.onopen = () => {
      setConnected(true);
      setRetryCount(0);
      console.log("WebSocket connection established");
    };
    
    // Handle messages
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Handle connection established message
        if (data.type === "connection_established") {
          clientIdRef.current = data.client_id;
          
          // Register for specific crew updates if crewId is provided
          if (crewId) {
            ws.send(JSON.stringify({
              type: "register_crew",
              crew_id: crewId
            }));
          }
          
          // Request initial state
          ws.send(JSON.stringify({
            type: "request_state"
          }));
          return;
        }
        
        // Handle crew registered confirmation
        if (data.type === "crew_registered") {
          console.log(`Registered for crew: ${data.crew_id}`);
          return;
        }
        
        // Handle state update
        if (data.crew || data.agents || data.tasks) {
          setState(prevState => {
            // Deep merge to avoid mutation issues
            const newState = {
              crew: data.crew || prevState.crew,
              agents: data.agents || prevState.agents,
              tasks: data.tasks || prevState.tasks
            };
            return newState;
          });
        }
      } catch (e) {
        console.error("Error processing WebSocket message:", e);
      }
    };
    
    // Handle connection close
    ws.onclose = (event) => {
      setConnected(false);
      console.log(`WebSocket disconnected: ${event.code} ${event.reason}`);
      
      // Implement reconnection with exponential backoff
      if (retryCount < maxRetries) {
        const delay = Math.min(1000 * Math.pow(2, retryCount), 30000);
        setTimeout(() => {
          setRetryCount(prev => prev + 1);
        }, delay);
      } else {
        setError("WebSocket connection failed after multiple attempts.");
      }
    };
    
    // Handle errors
    ws.onerror = (event) => {
      setError("WebSocket error");
      console.error("WebSocket error:", event);
    };
    
    // Store reference and handle cleanup
    wsRef.current = ws;
    return () => {
      ws.close();
    };
  }, [crewId, resetKey, retryCount]);
  
  // Set up heartbeat ping to keep connection alive
  useEffect(() => {
    if (!connected || !wsRef.current) return;
    
    const pingInterval = setInterval(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000); // Send ping every 30 seconds
    
    return () => clearInterval(pingInterval);
  }, [connected]);
  
  // Initialize crew on selection or reset
  useEffect(() => {
    if (!crewId) return;
    
    const initializeCrew = async () => {
      try {
        const response = await fetch(`/api/crews/${crewId}/initialize`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        
        if (!response.ok) {
          throw new Error(`Initialization failed: ${response.statusText}`);
        }
        
        const result = await response.json();
        console.log("Crew initialization result:", result);
      } catch (error) {
        console.error("Error initializing crew:", error);
        setError(`Failed to initialize crew: ${error.message}`);
      }
    };
    
    initializeCrew();
  }, [crewId, resetKey]);
  
  // Update nodes and edges when state changes
  useEffect(() => {
    if (!state.crew) return;
    
    // Generate nodes and edges based on state
    // ...existing node/edge generation logic...
    
    setNodes(newNodes);
    setEdges(newEdges);
  }, [state]);
  
  // Rest of the component remains similar...
}
```

#### 2.3 Update Kickoff Component

Modify the Kickoff component to handle crew selection and initialization:

```typescript
// In kickoff.tsx
export default function Kickoff() {
  // Existing state...
  const [selectedCrewId, setSelectedCrewId] = useState<string>("");
  const [resetKey, setResetKey] = useState(0);
  const [isInitializing, setIsInitializing] = useState(false);
  
  // Handle crew selection
  const handleCrewSelection = async (crewId: string) => {
    // Reset visualization state
    setResetKey(prev => prev + 1);
    setIsInitializing(true);
    setError(null);
    setResult(null);
    setIsRunningCrew(false);
    
    try {
      // Fetch crew details
      const response = await fetch(`/api/crews/${crewId}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch crew details: ${response.statusText}`);
      }
      
      const data = await response.json();
      setCrewDetails(data);
      setInputFields(data.required_inputs || []);
      
      // Update selected crew ID after successful fetch
      setSelectedCrewId(crewId);
    } catch (err) {
      setError(`Error selecting crew: ${err.message}`);
    } finally {
      setIsInitializing(false);
    }
  };
  
  // Modified useEffect for crew selection
  useEffect(() => {
    // If crews are already loaded and a valid selection hasn't been made yet
    if (crews.length > 0 && !selectedCrewId) {
      handleCrewSelection(crews[0].id);
    }
  }, [crews.length]);
  
  // Rest of component logic...
  
  return (
    <Layout>
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-6">Run a Crew</h1>
        
        {/* Crew selection */}
        <div className="mb-6">
          <Label htmlFor="crew-select" className="text-lg mb-2 block">
            Select a Crew
          </Label>
          <Select
            value={selectedCrewId}
            onValueChange={(value) => handleCrewSelection(value)}
            disabled={loading || isRunningCrew}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select a crew" />
            </SelectTrigger>
            <SelectContent>
              {crews.map((crew) => (
                <SelectItem key={crew.id} value={crew.id}>
                  {crew.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        
        {/* Initialization state */}
        {isInitializing && (
          <div className="mb-4">
            <div className="flex items-center">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              <span>Initializing crew visualization...</span>
            </div>
          </div>
        )}
        
        {/* Rest of the component... */}
        
        {/* Visualization */}
        <div className="mt-8 border rounded-lg p-4 bg-slate-50 min-h-[400px]">
          <h2 className="text-xl font-bold mb-4">Crew Visualization</h2>
          {selectedCrewId ? (
            <CrewAgentCanvas 
              crewId={selectedCrewId}
              isRunning={isRunningCrew}
              resetKey={resetKey}
            />
          ) : (
            <div className="text-center p-8 text-gray-500">
              Select a crew to view visualization
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
```

### Phase 3: Testing & Validation

#### 3.1 Backend Unit Tests

Create tests for the new initialization endpoints and event handlers:

```python
# In test_event_listener.py
def test_crew_initialization_events():
    """Test crew initialization event handling."""
    listener = CrewVisualizationListener()
    event_bus = Mock()
    
    # Test setup_listeners registers handlers correctly
    listener.setup_listeners(event_bus)
    assert event_bus.on.call_count >= 2  # At least CrewInitialization events
    
    # Test initialization requested handler
    init_event = CrewInitializationRequestedEvent(
        crew_id="test-crew",
        crew_name="Test Crew"
    )
    # Find and call the handler directly
    for call in event_bus.on.call_args_list:
        if call[0][0] == CrewInitializationRequestedEvent:
            handler = call[0][1]
            handler(Mock(), init_event)
            break
    
    # Verify state was reset and initialized
    assert listener.crew_state["id"] == "test-crew"
    assert listener.crew_state["name"] == "Test Crew"
    assert listener.crew_state["status"] == "initializing"
```

#### 3.2 Frontend Integration Tests

Create tests for the frontend components:

```typescript
// In CrewAgentCanvas.test.tsx
describe('CrewAgentCanvas', () => {
  let mockWebSocket: any;
  
  beforeEach(() => {
    // Mock WebSocket
    mockWebSocket = {
      send: jest.fn(),
      close: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    };
    
    // @ts-ignore
    global.WebSocket = jest.fn().mockImplementation(() => mockWebSocket);
    
    // Mock fetch for initialization
    global.fetch = jest.fn().mockImplementation(() => 
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: 'success' }),
      })
    );
  });
  
  it('initializes crew on mount', async () => {
    render(<CrewAgentCanvas crewId="test-crew" isRunning={false} />);
    
    // Should call initialization endpoint
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/crews/test-crew/initialize',
      expect.objectContaining({ method: 'POST' })
    );
    
    // Should create WebSocket connection
    expect(global.WebSocket).toHaveBeenCalledWith(
      expect.stringMatching(/ws:\/\/.+\/ws\/crew-visualization\/test-crew/)
    );
  });
  
  it('resets and reinitializes on crew change', async () => {
    const { rerender } = render(
      <CrewAgentCanvas crewId="crew-1" isRunning={false} />
    );
    
    // Clear mock calls from initial render
    (global.fetch as jest.Mock).mockClear();
    (global.WebSocket as jest.Mock).mockClear();
    
    // Rerender with different crew
    rerender(<CrewAgentCanvas crewId="crew-2" isRunning={false} />);
    
    // Should initialize new crew
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/crews/crew-2/initialize',
      expect.objectContaining({ method: 'POST' })
    );
    
    // Should create new WebSocket connection
    expect(global.WebSocket).toHaveBeenCalledWith(
      expect.stringMatching(/ws:\/\/.+\/ws\/crew-visualization\/crew-2/)
    );
  });
});
```

### Phase 4: Deployment and Documentation

#### 4.1 Deployment Checklist

1. Backend changes:
   - Add new event types
   - Update CrewVisualizationListener
   - Add initialization API endpoint
   - Update WebSocket endpoint

2. Frontend changes:
   - Update CrewAgentCanvas component
   - Update Kickoff component
   - Add error handling

#### 4.2 Documentation

Document the new initialization flow in developer docs:

```markdown
# Crew Initialization Flow

## Overview

The crew initialization flow allows for visualization of a crew's structure 
before execution. This is useful for understanding the agents and tasks in a crew.

## API Endpoints

### Initialize Crew

```
POST /api/crews/{crew_id}/initialize
```

Initializes a crew's structure without running it.

**Response:**
```json
{
  "status": "success",
  "message": "Crew {name} initialized",
  "crew_id": "{id}",
  "agent_count": 3,
  "task_count": 5
}
```

## WebSocket Protocol

### Connection

Connect to `/ws/crew-visualization/{crew_id}` to receive updates for a specific crew.

### Messages

**Client to Server:**
- `{ "type": "register_crew", "crew_id": "{id}" }` - Register for updates from a specific crew
- `{ "type": "request_state" }` - Request current state
- `{ "type": "ping" }` - Heartbeat ping

**Server to Client:**
- `{ "type": "connection_established", "client_id": "{id}" }` - Connection confirmation
- `{ "type": "crew_registered", "crew_id": "{id}" }` - Registration confirmation
- `{ "crew": {...}, "agents": [...], "tasks": [...] }` - State update

## React Component Usage

```tsx
<CrewAgentCanvas 
  crewId="example-crew" 
  isRunning={false} 
  resetKey={0} // Change to force reset
/>
```
```

## Implementation Timeline

### Week 1: Core Backend Changes
- Day 1-2: Implement event types and listener updates
- Day 3-4: Create initialization API endpoint
- Day 5: Unit tests for backend changes

### Week 2: Frontend Implementation
- Day 1-2: Update CrewAgentCanvas component
- Day 3-4: Update Kickoff component and add error handling
- Day 5: Integration tests

### Week 3: Testing & Refinement
- Day 1-2: Manual testing and bug fixes
- Day 3: Performance optimization
- Day 4-5: Documentation and final polish

## Success Criteria

The implementation will be considered successful when:

1. Users can select a new crew and see its structure immediately
2. The visualization resets properly between crew changes
3. The system provides clear feedback during initialization
4. WebSocket connections are efficiently managed
5. Error states are handled gracefully
6. All tests pass and no new bugs are introduced

## Conclusion

This enhancement will significantly improve the user experience by providing immediate visual feedback when selecting different crews. The clear initialization state and improved error handling will make the system more robust and user-friendly.
