import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useLocation } from "react-router";
import { Card } from "../components/ui/card";
import { Loader2, ExternalLink, BarChart3, Activity, Play } from "lucide-react";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";
import ReactMarkdown from "react-markdown";
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  Background,
  Controls,
  MiniMap,
  Position,
  MarkerType,
  ConnectionLineType,
  Handle,
  applyNodeChanges,
  applyEdgeChanges,
  useReactFlow,
} from "@xyflow/react";
import type { 
  NodeTypes, 
  Node, 
  Edge, 
  NodeProps,
  NodeChange,
  EdgeChange,
  ReactFlowInstance 
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";

// Define domain models
interface Agent {
  id: string;
  role: string;
  name: string;
  status: "initializing" | "waiting" | "running" | "completed";
  description: string;
}

interface Task {
  id: string;
  description: string;
  status: "pending" | "running" | "completed";
  agent_id: string | null;
  output?: string | Record<string, unknown>;
  next_tasks?: string[];
  depends_on?: string[];
}

interface Crew {
  id: string;
  name: string;
  status: "initializing" | "running" | "completed";
  started_at?: string;
  completed_at?: string;
  output?: string;
  type?: "sequential" | "hierarchical";
  execution_order?: string[];
}

// Define custom node data types
interface AgentNodeData extends Agent {
  associatedTasks?: Task[];
  isFirst?: boolean;
  isLast?: boolean;
  uniformWidth?: number;
  uniformHeight?: number;
  hasIncomingEdge?: boolean;
  hasOutgoingEdge?: boolean;
  [key: string]: unknown;
}

interface TaskNodeData extends Task {
  assignedAgentName?: string;
  uniformWidth?: number;
  uniformHeight?: number;
  hasIncomingEdge?: boolean;
  hasOutgoingEdge?: boolean;
  [key: string]: unknown;
}

interface CrewNodeData extends Crew {
  uniformWidth?: number;
  uniformHeight?: number;
  hasIncomingEdge?: boolean;
  hasOutgoingEdge?: boolean;
  [key: string]: unknown;
}

interface VisualizationState {
  crew: Crew | null;
  agents: Agent[];
  tasks: Task[];
  timestamp?: string;
}

interface CrewAgentCanvasProps {
  crewId: string;
  isRunning: boolean;
  resetKey?: number; // Key that changes to trigger state reset
}

// Helper function for status colors
const getStatusColor = (status: string): string => {
  switch (status) {
    case "completed":
      return "#6366f1"; // indigo-500
    case "running":
      return "#10b981"; // emerald-500
    case "waiting":
      return "#f59e0b"; // amber-500
    case "initializing":
      return "#3b82f6"; // blue-500
    case "pending":
      return "#64748b"; // slate-500
    default:
      return "#64748b"; // slate-500
  }
}

// Initialize dagre graph
const dagreGraph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));

// Calculate maximum dimensions for all nodes to ensure uniform sizing
const calculateMaxNodeDimensions = (nodes: Node[]): { width: number; height: number } => {
  // Default minimum dimensions
  const defaultWidth = 280;
  const defaultHeight = 150;
  
  return { width: defaultWidth, height: defaultHeight };
}

// Layout the nodes and edges using dagre
const getLayoutedElements = (
  nodes: Node[],
  edges: Edge[],
  direction: 'TB' | 'LR' = 'TB'
): { nodes: Node[]; edges: Edge[]; fullWidth: number; fullHeight: number } => {
  if (!nodes.length) return { nodes, edges, fullWidth: 0, fullHeight: 0 };

  // Get max dimensions to ensure uniform sizing
  const { width: maxWidth, height: maxHeight } = calculateMaxNodeDimensions(nodes);
  const nodeWidth = Math.max(maxWidth, 320); // Increased minimum width for task details
  const nodeHeight = Math.max(maxHeight, 200); // Increased minimum height for task details

  // Create a new directed graph with optimized spacing for vertical layout
  dagreGraph.setGraph({ 
    rankdir: direction, 
    nodesep: 50, // Horizontal spacing between nodes (reduced for center alignment)
    ranksep: 120, // Vertical spacing between ranks
    align: 'UL', // Align nodes to upper-left for consistent positioning
    marginx: 20,
    marginy: 20
  });

  // Add nodes to the graph with uniform dimensions
  nodes.forEach((node) => {
    // Add uniform dimensions to node data for rendering
    if (node.data) {
      node.data.uniformWidth = nodeWidth;
      node.data.uniformHeight = nodeHeight;
    }

    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  // Add edges to the graph
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Run the layout algorithm
  dagre.layout(dagreGraph);

  // Get graph dimensions for viewport adjustments
  const graphData = dagreGraph.graph();
  const fullWidth = graphData && graphData.width ? graphData.width / 2 : 0;
  const fullHeight = graphData && graphData.height ? graphData.height / 2 : 0;

  // Update node positions based on the dagre layout results
  const layoutedNodes = nodes.map((node) => {
    const dagreNode = dagreGraph.node(node.id);

    if (!dagreNode) {
      console.warn(`No dagre node found for id: ${node.id}`);
      return node;
    }

    return {
      ...node,
      position: {
        x: dagreNode.x - nodeWidth / 2,
        y: dagreNode.y - nodeHeight / 2,
      },
      // Store uniform dimensions in the node data for CSS styling
      data: {
        ...node.data,
        uniformWidth: nodeWidth,
        uniformHeight: nodeHeight,
      },
    };
  });

  return { nodes: layoutedNodes, edges, fullWidth, fullHeight };
};

// Custom node components
const AgentNode: React.FC<NodeProps> = ({ data, id }) => {
  const typedData = data as unknown as AgentNodeData;
  const statusColor = getStatusColor(typedData.status);
  
  // Check if this node has incoming or outgoing connections
  const hasIncomingEdge = typedData.hasIncomingEdge ?? false;
  const hasOutgoingEdge = typedData.hasOutgoingEdge ?? false;

  return (
    <div
      className="px-4 py-3 shadow-md rounded-md bg-white border-2"
      style={{ 
        borderColor: statusColor,
        width: typedData.uniformWidth ? `${typedData.uniformWidth}px` : '320px',
        minHeight: typedData.uniformHeight ? `${typedData.uniformHeight}px` : '180px'
      }}
    >
      <div className="flex justify-between items-center">
        <div className="font-bold text-sm">{typedData.role}</div>
        <div
          className="rounded-full w-3 h-3"
          style={{ backgroundColor: statusColor }}
        ></div>
      </div>
      <div className="text-xs text-gray-500 mt-1">{typedData.name}</div>
      <div className="mt-2 text-xs">
        {typedData.description && typedData.description.length > 80
          ? `${typedData.description.substring(0, 80)}...`
          : typedData.description}
      </div>
      
      {/* Tasks Section - Always Visible */}
      {typedData.associatedTasks && typedData.associatedTasks.length > 0 && (
        <div className="mt-3 border-t pt-2">
          <div className="text-xs font-semibold mb-1">Tasks:</div>
          <div className="space-y-2">
            {typedData.associatedTasks.map((task) => (
              <div 
                key={task.id}
                className="text-xs p-2 rounded bg-gray-50 border border-gray-100"
                style={{
                  borderLeft: `3px solid ${getStatusColor(task.status)}`
                }}
              >
                {/* Task Header with Description and Status */}
                <div className="flex justify-between items-center">
                  <div className="font-medium">
                    {task.description.length > 50
                      ? `${task.description.substring(0, 50)}...`
                      : task.description}
                  </div>
                  <div className="ml-1 text-[10px] px-1.5 py-0.5 rounded-full font-medium" 
                    style={{ 
                      backgroundColor: getStatusColor(task.status),
                      color: 'white',
                      opacity: 0.9
                    }}>
                    {task.status}
                  </div>
                </div>
                
                {/* Task Output - Always Visible */}
                {task.output && (
                  <div className="mt-1.5">
                    <div className="text-[10px] text-gray-500 font-medium">Output:</div>
                    <div className="whitespace-pre-wrap overflow-hidden max-h-16 overflow-y-auto text-[10px] mt-0.5">
                      {typeof task.output === 'string' 
                        ? task.output.substring(0, 120) + (task.output.length > 120 ? '...' : '')
                        : JSON.stringify(task.output, null, 2).substring(0, 120) + '...'}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* Only render target handle if this node has incoming connections */}
      {hasIncomingEdge && (
        <Handle
          type="target"
          position={Position.Top}
          className="w-2 h-2 bg-blue-500"
          isConnectable={false}
        />
      )}
      
      {/* Only render source handle if this node has outgoing connections */}
      {hasOutgoingEdge && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="w-2 h-2 bg-blue-500"
          isConnectable={false}
        />
      )}
    </div>
  );
};

const TaskNode: React.FC<NodeProps> = ({ data }) => {
  const typedData = data as unknown as TaskNodeData;
  const statusColor = getStatusColor(typedData.status);
  
  // Check if this node has incoming or outgoing connections
  const hasIncomingEdge = typedData.hasIncomingEdge ?? false;
  const hasOutgoingEdge = typedData.hasOutgoingEdge ?? false;

  return (
    <div
      className="px-4 py-2 shadow-md rounded-md bg-white border-2 w-[280px]"
      style={{ borderColor: statusColor }}
    >
      <div className="flex justify-between items-center">
        <div className="font-bold text-sm">Task</div>
        <div
          className="rounded-full w-3 h-3"
          style={{ backgroundColor: statusColor }}
        ></div>
      </div>
      {typedData.assignedAgentName && (
        <div className="text-xs text-gray-500 mt-1">
          Assigned to: {typedData.assignedAgentName}
        </div>
      )}
      <div className="mt-2 text-xs">
        {typedData.description && typedData.description.length > 100
          ? `${typedData.description.substring(0, 100)}...`
          : typedData.description}
      </div>
      
      {/* Only render target handle if this node has incoming connections */}
      {hasIncomingEdge && (
        <Handle
          type="target"
          position={Position.Top}
          className="w-2 h-2 bg-blue-500"
          isConnectable={false}
        />
      )}
      
      {/* Only render source handle if this node has outgoing connections */}
      {hasOutgoingEdge && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="w-2 h-2 bg-blue-500"
          isConnectable={false}
        />
      )}
    </div>
  );
};

const CrewNode: React.FC<NodeProps> = ({ data }) => {
  const typedData = data as unknown as CrewNodeData;
  const statusColor = getStatusColor(typedData.status);

  return (
    <div
      className="px-4 py-3 shadow-md rounded-md bg-white border-2 flex flex-col justify-center"
      style={{ 
        borderColor: statusColor,
        width: typedData.uniformWidth ? `${typedData.uniformWidth}px` : '320px',
        minHeight: typedData.uniformHeight ? `${typedData.uniformHeight}px` : '200px'
      }}
    >
      <div className="flex justify-between items-center mb-2">
        <div className="font-bold text-lg">🚀 Crew</div>
        <div
          className="rounded-full w-4 h-4"
          style={{ backgroundColor: statusColor }}
        ></div>
      </div>
      <div className="text-sm font-medium text-gray-700 mb-1">{typedData.name}</div>
      <div className="text-xs text-gray-500 mb-2">Status: {typedData.status}</div>
      
      {/* Crew Details */}
      <div className="mt-auto pt-2 border-t border-gray-100">
        <div className="text-xs text-gray-600">
          <div>Type: {typedData.type || 'Sequential'}</div>
          {typedData.started_at && (
            <div className="mt-1">Started: {new Date(typedData.started_at).toLocaleTimeString()}</div>
          )}
        </div>
      </div>
      
      {/* Crew node has no handles as per requirements */}
    </div>
  );
};

const CrewAgentCanvas: React.FC<CrewAgentCanvasProps> = ({
  crewId,
  isRunning,
  resetKey = 0,
}) => {
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const clientIdRef = useRef<string | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const heartbeatIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // State variables
  const [state, setState] = useState<VisualizationState>({
    crew: null,
    agents: [],
    tasks: [],
  });
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );
  const [connectionStatus, setConnectionStatus] = useState<
    "connecting" | "connected" | "disconnected"
  >("connecting");
  const [isInitializing, setIsInitializing] = useState<boolean>(false);
  const [hasReceivedData, setHasReceivedData] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Define node types
  const nodeTypes: NodeTypes = {
    agent: AgentNode,
    task: TaskNode,
    crew: CrewNode,
  };

  // Initialize crew function
  const initializeCrew = useCallback(async (crewId: string) => {
    if (!crewId) return;

    setIsInitializing(true);
    setError(null);

    try {
      const response = await fetch(`/api/crews/${crewId}/initialize`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || "Failed to initialize crew");
      }

      console.log("Crew initialization successful:", data);
    } catch (err) {
      console.error("Error initializing crew:", err);
      setError(
        `Failed to initialize crew: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    } finally {
      setIsInitializing(false);
    }
  }, []);

  // WebSocket connection function
  const connectWebSocket = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log("WebSocket already connected");
      return;
    }

    // Clear any existing reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Clear any existing heartbeat interval
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }

    setConnectionStatus("connecting");

    try {
      // Create WebSocket connection with crew ID in the URL
      const wsUrl = `${
        window.location.protocol === "https:" ? "wss:" : "ws:"
      }//${window.location.host}/ws/crew-visualization/${crewId}`;
      console.log(`Connecting to WebSocket at ${wsUrl}`);

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("WebSocket connection established");
        reconnectAttemptsRef.current = 0; // Reset reconnect attempts on successful connection
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Handle connection established message
          if (data.type === "connection_established") {
            setConnectionStatus("connected");
            clientIdRef.current = data.client_id;
            console.log(
              `Connection established with client ID: ${data.client_id}`
            );

            // Register for crew updates
            if (crewId) {
              ws.send(
                JSON.stringify({
                  type: "register_crew",
                  crew_id: crewId,
                })
              );
            }

            // Set up heartbeat ping every 30 seconds
            heartbeatIntervalRef.current = setInterval(() => {
              if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "ping" }));
              }
            }, 30000);

            // Request current state
            ws.send(JSON.stringify({ type: "request_state" }));
          }
          // Handle crew registration confirmation
          else if (data.type === "crew_registered") {
            console.log(`Registered for crew: ${data.crew_id}`);
          }
          // Handle pong response (heartbeat)
          else if (data.type === "pong") {
            console.log("Heartbeat pong received");
          }
          // Handle state update - check for crew visualization data
          else if (data.crew !== undefined || data.agents !== undefined || data.tasks !== undefined) {
            console.log("🔄 Received crew visualization data:", {
              crew: data.crew ? { id: data.crew.id, status: data.crew.status, hasOutput: !!data.crew.output } : null,
              agents: data.agents ? data.agents.length : 0,
              tasks: data.tasks ? data.tasks.length : 0,
              timestamp: data.timestamp
            });

            // Merge new state with existing state
            setState((prevState) => {
              const newState = { ...prevState };

              if (data.crew !== undefined) {
                newState.crew = data.crew;
                console.log("✅ Updated crew state:", {
                  id: data.crew?.id,
                  status: data.crew?.status,
                  hasOutput: !!data.crew?.output,
                  outputLength: data.crew?.output ? data.crew.output.length : 0
                });
                
                // Log when crew completes with output
                if (data.crew?.status === "completed" && data.crew?.output) {
                  console.log("🎉 Crew completed with output! Result will be displayed.");
                }
              }

              if (data.agents !== undefined) {
                // Create a map of existing agents for efficient lookup
                const agentMap = new Map(
                  prevState.agents.map((agent) => [agent.id, agent])
                );

                // Update or add agents from the new data
                data.agents.forEach((agent: Agent) => {
                  agentMap.set(agent.id, agent);
                });

                newState.agents = Array.from(agentMap.values());
                console.log("👥 Updated agents:", newState.agents.map(a => ({ id: a.id, status: a.status })));
              }

              if (data.tasks !== undefined) {
                // Create a map of existing tasks for efficient lookup
                const taskMap = new Map(
                  prevState.tasks.map((task) => [task.id, task])
                );

                // Update or add tasks from the new data
                data.tasks.forEach((task: Task) => {
                  taskMap.set(task.id, task);
                });

                newState.tasks = Array.from(taskMap.values());
                console.log("📋 Updated tasks:", newState.tasks.map(t => ({ id: t.id, status: t.status })));
              }

              if (data.timestamp) {
                newState.timestamp = data.timestamp;
              }

              return newState;
            });

            // Always set hasReceivedData to true when we get crew visualization data
            console.log("✅ Setting hasReceivedData to true");
            setHasReceivedData(true);
          }
          // Fallback: if data has any crew-related properties, treat as state update
          else if (typeof data === 'object' && data !== null && 
                   ('crew' in data || 'agents' in data || 'tasks' in data || 'timestamp' in data)) {
            console.log("Fallback: Received potential crew data:", data);
            
            // Set received data flag even for fallback case
            setHasReceivedData(true);
            
            // Try to update state with available data
            setState((prevState) => {
              const newState = { ...prevState };
              
              if ('crew' in data && data.crew) {
                newState.crew = data.crew as any;
              }
              if ('agents' in data && data.agents) {
                newState.agents = data.agents as any;
              }
              if ('tasks' in data && data.tasks) {
                newState.tasks = data.tasks as any;
              }
              if ('timestamp' in data && data.timestamp) {
                newState.timestamp = data.timestamp as any;
              }
              
              return newState;
            });
          }
        } catch (err) {
          console.error("Error processing WebSocket message:", err);
        }
      };

      ws.onclose = (event) => {
        console.log(
          `WebSocket connection closed: ${event.code} ${event.reason}`
        );
        setConnectionStatus("disconnected");

        // Clear heartbeat interval
        if (heartbeatIntervalRef.current) {
          clearInterval(heartbeatIntervalRef.current);
          heartbeatIntervalRef.current = null;
        }

        // Attempt to reconnect with exponential backoff
        if (reconnectAttemptsRef.current < 5) {
          const delay = Math.min(
            1000 * 2 ** reconnectAttemptsRef.current,
            30000
          );
          console.log(
            `Attempting to reconnect in ${delay}ms (attempt ${
              reconnectAttemptsRef.current + 1
            }/5)`
          );

          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current += 1;
            connectWebSocket();
          }, delay);
        } else {
          console.log("Maximum reconnection attempts reached");
          setError(
            "Failed to connect to visualization service after multiple attempts. Please try again later."
          );
        }
      };

      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        setError("Error connecting to visualization service");
      };
    } catch (err) {
      console.error("Error setting up WebSocket:", err);
      setConnectionStatus("disconnected");
      setError(
        `Failed to connect: ${err instanceof Error ? err.message : String(err)}`
      );
    }
  }, [crewId]);

  // Reset state when crew ID changes (WebSocket reconnection)
  useEffect(() => {
    // Reset state
    setState({
      crew: null,
      agents: [],
      tasks: [],
    });
    setHasReceivedData(false);
    setError(null);

    // Close existing WebSocket connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Clear any existing timeouts/intervals
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }

    // Reset reconnect attempts
    reconnectAttemptsRef.current = 0;

    if (crewId) {
      // Initialize crew first
      initializeCrew(crewId).then(() => {
        // Then connect to WebSocket
        connectWebSocket();
      });
    }

    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current);
        heartbeatIntervalRef.current = null;
      }
    };
  }, [crewId, connectWebSocket, initializeCrew]); // Removed resetKey from dependencies

  // Reset state when resetKey changes (without WebSocket reconnection)
  useEffect(() => {
    // Only reset state, don't reconnect WebSocket
    setState({
      crew: null,
      agents: [],
      tasks: [],
    });
    setHasReceivedData(false);
    setError(null);
    
    console.log(`State reset triggered by resetKey: ${resetKey}`);
  }, [resetKey]);

  // Center the graph when nodes change or when a new crew is selected
  useEffect(() => {
    if (reactFlowInstance && nodes.length > 0) {
      // Use a small timeout to ensure the graph is rendered before centering
      setTimeout(() => {
        reactFlowInstance.fitView({ padding: 0.2 });
      }, 50);
    }
  }, [nodes.length, reactFlowInstance, crewId, resetKey]);

  // Update nodes and edges when state changes
  useEffect(() => {
    if (!state.crew && !state.agents.length && !state.tasks.length) {
      return;
    }

    const newNodes: Node[] = [];
    const newEdges: Edge[] = [];

    // 1. Create crew node if available (crew node has no handles)
    if (state.crew) {
      const crewNode = {
        id: `crew-${state.crew.id}`,
        type: "crew",
        position: { x: 0, y: 0 }, // Position will be set by dagre layout
        data: {
          ...state.crew,
          // Crew node never has handles
          hasOutgoingEdge: false,
          hasIncomingEdge: false,
        },
      } as Node;

      newNodes.push(crewNode);
    }

    // 2. Create agent nodes in execution order
    let orderedAgents: Agent[] = [];
    
    // Use execution order if available, otherwise use agent array order
    if (state.crew?.execution_order && state.crew.execution_order.length > 0) {
      // Order agents based on execution_order
      orderedAgents = state.crew.execution_order
        .map(agentId => state.agents.find(a => a.id === agentId))
        .filter(agent => agent !== undefined) as Agent[];
      
      // Add any agents not in execution_order at the end
      const agentsInOrder = new Set(orderedAgents.map(a => a.id));
      const remainingAgents = state.agents.filter(a => !agentsInOrder.has(a.id));
      orderedAgents = [...orderedAgents, ...remainingAgents];
    } else {
      // Fallback to original agent order
      orderedAgents = [...state.agents];
    }

    orderedAgents.forEach((agent: Agent, index: number) => {
      // Find tasks assigned to this agent
      const agentTasks = state.tasks.filter(
        (task) => task.agent_id === agent.id
      );

      // Determine handle visibility based on execution position
      const isFirstAgent = index === 0;
      const isLastAgent = index === orderedAgents.length - 1;
      
      // First agent has input handle from crew, last agent has no output handle
      const hasIncomingEdge = true; // All agents have incoming edges (first from crew, others from previous agent)
      const hasOutgoingEdge = !isLastAgent;
      
      const agentNode = {
        id: `agent-${agent.id}`,
        type: "agent",
        position: { x: 0, y: 0 }, // Position will be set by dagre layout
        data: {
          ...agent,
          associatedTasks: agentTasks,
          isFirst: isFirstAgent,
          isLast: isLastAgent,
          hasIncomingEdge: hasIncomingEdge,
          hasOutgoingEdge: hasOutgoingEdge,
          executionOrder: index, // Add execution order for debugging
        },
      } as Node;

      newNodes.push(agentNode);
    });

    // 3. Create edges between consecutive agents in execution order
    for (let i = 0; i < orderedAgents.length - 1; i++) {
      const currentAgent = orderedAgents[i];
      const nextAgent = orderedAgents[i + 1];
      
      const sourceId = `agent-${currentAgent.id}`;
      const targetId = `agent-${nextAgent.id}`;

      // Determine edge color based on current agent status
      let edgeColor = "#64748b"; // default slate-500
      let animated = false;

      if (currentAgent.status === "completed") {
        edgeColor = "#6366f1"; // indigo-500 for completed
      } else if (currentAgent.status === "running") {
        edgeColor = "#10b981"; // emerald-500 for running
        animated = true;
      } else if (currentAgent.status === "waiting") {
        edgeColor = "#f59e0b"; // amber-500 for waiting
      }

      const agentEdge: Edge = {
        id: `agent-${currentAgent.id}-to-${nextAgent.id}`,
        source: sourceId,
        target: targetId,
        type: "default",
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: edgeColor,
        },
        style: {
          strokeWidth: 2,
          stroke: edgeColor,
        },
        animated: animated,
      };

      newEdges.push(agentEdge);
    }

    // 4. Connect crew node to first agent for perfect vertical layout
    if (state.crew && orderedAgents.length > 0) {
      const firstAgent = orderedAgents[0];
      const crewToFirstAgentEdge: Edge = {
        id: `crew-${state.crew.id}-to-agent-${firstAgent.id}`,
        source: `crew-${state.crew.id}`,
        target: `agent-${firstAgent.id}`,
        type: "default",
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: "#64748b",
        },
        style: {
          strokeWidth: 2,
          stroke: "#64748b",
        },
      };
      newEdges.push(crewToFirstAgentEdge);
    }
    
    // Apply dagre layout to position nodes automatically
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      newNodes,
      newEdges,
      'TB' // Top to bottom layout direction
    );

    // Update nodes and edges with the layouted positions
    setNodes(layoutedNodes as Node[]);
    setEdges(layoutedEdges as Edge[]);
  }, [state, setNodes, setEdges]);

  // Get current location to determine active tab
  const location = useLocation();
  const path = location.pathname;
  
  // Extract effective crew ID for navigation
  const effectiveCrewId = state.crew?.id || crewId;

  return (
    <Card className="p-6 mb-6 overflow-hidden relative">
      {/* Navigation menu moved to kickoff.tsx */}
      
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Crew Execution Visualization</h3>
      </div>

      {/* Loading state */}
      {!hasReceivedData && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/80 dark:bg-slate-900/80 z-10">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mb-4" />
          <h3 className="text-lg font-medium">
            {isInitializing
              ? "Initializing crew..."
              : isRunning
              ? "Waiting for data..."
              : "Loading visualization..."}
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {isInitializing
              ? "Setting up the crew structure..."
              : isRunning
              ? "The crew execution will appear here once it starts"
              : "Connecting to visualization service..."}
          </p>
          <div className="mt-4 flex items-center space-x-2">
            <div
              className={`h-2 w-2 rounded-full ${
                connectionStatus === "connected"
                  ? "bg-green-500"
                  : connectionStatus === "connecting"
                  ? "bg-amber-500"
                  : "bg-red-500"
              }`}
            ></div>
            <span className="text-xs">
              {connectionStatus === "connected"
                ? "Connected"
                : connectionStatus === "connecting"
                ? "Connecting..."
                : "Disconnected"}
            </span>
            {connectionStatus === "disconnected" && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => connectWebSocket()}
                className="ml-2"
              >
                Reconnect
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* React Flow Canvas */}
      <div
        className="h-[600px] border rounded-md overflow-hidden mb-6"
        ref={canvasRef}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          attributionPosition="bottom-right"
          defaultEdgeOptions={{
            type: "default",
            markerEnd: { type: MarkerType.ArrowClosed },
          }}
          connectionLineType={ConnectionLineType.SmoothStep}
          proOptions={{ hideAttribution: true }}
          minZoom={0.5}
          maxZoom={1.5}
          elementsSelectable={true}
          onInit={setReactFlowInstance}
        >
          <Background color="#aaa" gap={16} />
          <Controls />
          <MiniMap nodeStrokeWidth={3} zoomable pannable />
        </ReactFlow>
      </div>

      {/* Crew Results Section */}
      {state.crew?.status === "completed" && state.crew?.output && (
        <div className="mt-4">
          <h3 className="text-lg font-semibold mb-4">Crew Results</h3>
          <div className="p-6 rounded-lg border bg-card overflow-auto">
            <div className="text-base leading-7">
              <ReactMarkdown
                components={{
                  h1: ({ ...props }: React.ComponentPropsWithoutRef<"h1">) => (
                    <h1 className="text-2xl font-bold mt-6 mb-4" {...props} />
                  ),
                  h2: ({ ...props }: React.ComponentPropsWithoutRef<"h2">) => (
                    <h2 className="text-xl font-bold mt-5 mb-3" {...props} />
                  ),
                  h3: ({ ...props }: React.ComponentPropsWithoutRef<"h3">) => (
                    <h3 className="text-lg font-bold mt-4 mb-2" {...props} />
                  ),
                  p: ({ ...props }: React.ComponentPropsWithoutRef<"p">) => (
                    <p className="mb-4" {...props} />
                  ),
                  ul: ({ ...props }: React.ComponentPropsWithoutRef<"ul">) => (
                    <ul className="list-disc pl-6 mb-4" {...props} />
                  ),
                  ol: ({ ...props }: React.ComponentPropsWithoutRef<"ol">) => (
                    <ol className="list-decimal pl-6 mb-4" {...props} />
                  ),
                  li: ({ ...props }: React.ComponentPropsWithoutRef<"li">) => (
                    <li className="mb-1" {...props} />
                  ),
                  a: ({ ...props }: React.ComponentPropsWithoutRef<"a">) => (
                    <a className="text-blue-500 hover:underline" {...props} />
                  ),
                  blockquote: ({
                    ...props
                  }: React.ComponentPropsWithoutRef<"blockquote">) => (
                    <blockquote
                      className="border-l-4 border-muted pl-4 italic my-4"
                      {...props}
                    />
                  ),
                  code: (props) => {
                    // Using a simpler approach to avoid TypeScript errors
                    const { children, className } = props;
                    const match = /language-(\w+)/.exec(className || "");
                    const isInline =
                      !match &&
                      (typeof children === "string"
                        ? !children.includes("\n")
                        : true);
                    return isInline ? (
                      <code className="bg-muted px-1 py-0.5 rounded" {...props}>
                        {children}
                      </code>
                    ) : (
                      <pre className="p-4 rounded-md bg-muted overflow-x-auto">
                        <code className={className}>{children}</code>
                      </pre>
                    );
                  },
                }}
              >
                {state.crew.output}
              </ReactMarkdown>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
};

export default CrewAgentCanvas;
