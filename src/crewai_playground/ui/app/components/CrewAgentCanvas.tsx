import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router";
import { Card } from "../components/ui/card";
import { Loader2, ExternalLink } from "lucide-react";
import { Button } from "../components/ui/button";
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
} from "@xyflow/react";
import type { NodeTypes, Node, Edge, NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

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
interface BaseNodeData {
  [key: string]: unknown;
  isFirst?: boolean;
  isLast?: boolean;
}

interface AgentNodeData extends BaseNodeData {
  id: string;
  role: string;
  name: string;
  status: "initializing" | "waiting" | "running" | "completed";
  description: string;
  associatedTasks?: Task[];
}

interface TaskNodeData extends BaseNodeData {
  id: string;
  description: string;
  status: "pending" | "running" | "completed";
  agent_id: string | null;
  output?: string | Record<string, unknown>;
  assignedAgentName?: string;
  next_tasks?: string[];
  depends_on?: string[];
}

interface CrewNodeData extends BaseNodeData {
  id: string;
  name: string;
  status: "initializing" | "running" | "completed";
  started_at?: string;
  completed_at?: string;
  output?: string;
  type?: "sequential" | "hierarchical";
  execution_order?: string[];
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
};

// Custom node components
const AgentNode: React.FC<NodeProps> = ({ data }) => {
  const typedData = data as AgentNodeData;
  const statusColor = getStatusColor(typedData.status);

  return (
    <div
      className="px-4 py-2 shadow-md rounded-md bg-white border-2 w-[280px]"
      style={{ borderColor: statusColor }}
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
        {typedData.description && typedData.description.length > 100
          ? `${typedData.description.substring(0, 100)}...`
          : typedData.description}
      </div>
      <Handle
        type="target"
        position={Position.Top}
        className="w-2 h-2 bg-blue-500"
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2 h-2 bg-blue-500"
        isConnectable={false}
      />
    </div>
  );
};

const TaskNode: React.FC<NodeProps> = ({ data }) => {
  const typedData = data as TaskNodeData;
  const statusColor = getStatusColor(typedData.status);

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
      <Handle
        type="target"
        position={Position.Top}
        className="w-2 h-2 bg-blue-500"
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2 h-2 bg-blue-500"
        isConnectable={false}
      />
    </div>
  );
};

const CrewNode: React.FC<NodeProps> = ({ data }) => {
  const typedData = data as CrewNodeData;
  const statusColor = getStatusColor(typedData.status);

  return (
    <div
      className="px-4 py-2 shadow-md rounded-md bg-white border-2 w-[280px]"
      style={{ borderColor: statusColor }}
    >
      <div className="flex justify-between items-center">
        <div className="font-bold text-sm">Crew</div>
        <div
          className="rounded-full w-3 h-3"
          style={{ backgroundColor: statusColor }}
        ></div>
      </div>
      <div className="text-xs text-gray-500 mt-1">{typedData.name}</div>
      <div className="mt-2 text-xs">Status: {typedData.status}</div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2 h-2 bg-blue-500"
        isConnectable={false}
      />
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
  const initialNodes: Node[] = [];
  const initialEdges: Edge[] = [];
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
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
          // Handle state update
          else if (data.crew || data.agents || data.tasks) {
            console.log("Received state update:", data);

            // Merge new state with existing state
            setState((prevState) => {
              const newState = { ...prevState };

              if (data.crew) {
                newState.crew = data.crew;
              }

              if (data.agents) {
                // Create a map of existing agents for efficient lookup
                const agentMap = new Map(
                  prevState.agents.map((agent) => [agent.id, agent])
                );

                // Update or add agents from the new data
                data.agents.forEach((agent: Agent) => {
                  agentMap.set(agent.id, agent);
                });

                newState.agents = Array.from(agentMap.values());
              }

              if (data.tasks) {
                // Create a map of existing tasks for efficient lookup
                const taskMap = new Map(
                  prevState.tasks.map((task) => [task.id, task])
                );

                // Update or add tasks from the new data
                data.tasks.forEach((task: Task) => {
                  taskMap.set(task.id, task);
                });

                newState.tasks = Array.from(taskMap.values());
              }

              if (data.timestamp) {
                newState.timestamp = data.timestamp;
              }

              return newState;
            });

            setHasReceivedData(true);
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

  // Reset state when crew ID changes
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
  }, [crewId, resetKey, connectWebSocket, initializeCrew]);

  // Update nodes and edges when state changes
  useEffect(() => {
    if (!state.crew && !state.agents.length && !state.tasks.length) {
      return;
    }

    const newNodes: Node[] = [];
    const newEdges: Edge[] = [];

    // 1. Create crew node if available
    if (state.crew) {
      const crewNode: Node<CrewNodeData> = {
        id: `crew-${state.crew.id}`,
        type: "crew",
        position: { x: 400, y: 50 },
        data: {
          ...state.crew,
        },
      };

      newNodes.push(crewNode);
    }

    // 2. Create agent nodes
    // Sort agents by status to show running first, then waiting, then completed
    const sortedAgents = [...state.agents].sort((a, b) => {
      const statusOrder: Record<string, number> = {
        running: 0,
        waiting: 1,
        initializing: 2,
        completed: 3,
      };

      return (statusOrder[a.status] || 99) - (statusOrder[b.status] || 99);
    });

    sortedAgents.forEach((agent, index) => {
      // Find tasks assigned to this agent
      const agentTasks = state.tasks.filter(
        (task) => task.agent_id === agent.id
      );

      const agentNode: Node<AgentNodeData> = {
        id: `agent-${agent.id}`,
        type: "agent",
        position: {
          x: 200 + (index % 3) * 300,
          y: 200 + Math.floor(index / 3) * 150,
        },
        data: {
          ...agent,
          associatedTasks: agentTasks,
          isFirst: index === 0,
          isLast: index === sortedAgents.length - 1,
        },
      };

      newNodes.push(agentNode);

      // Connect crew to first agent
      if (state.crew && index === 0) {
        const crewToAgentEdge: Edge = {
          id: `crew-${state.crew.id}-to-agent-${agent.id}`,
          source: `crew-${state.crew.id}`,
          target: `agent-${agent.id}`,
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

        newEdges.push(crewToAgentEdge);
      }

      // Create task nodes for this agent
      agentTasks.forEach((task, taskIndex) => {
        const taskNode: Node<TaskNodeData> = {
          id: `task-${task.id}`,
          type: "task",
          position: {
            x: 200 + (index % 3) * 300,
            y: 300 + Math.floor(index / 3) * 150 + taskIndex * 100,
          },
          data: {
            ...task,
            assignedAgentName: agent.name,
          },
        };

        newNodes.push(taskNode);

        // Connect agent to task
        const agentToTaskEdge: Edge = {
          id: `agent-${agent.id}-to-task-${task.id}`,
          source: `agent-${agent.id}`,
          target: `task-${task.id}`,
          type: "default",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: getStatusColor(task.status),
          },
          style: {
            strokeWidth: 2,
            stroke: getStatusColor(task.status),
          },
          animated: task.status === "running",
        };

        newEdges.push(agentToTaskEdge);
      });
    });

    // 3. Create edges between agents in sequence
    for (let i = 0; i < sortedAgents.length - 1; i++) {
      const currentAgent = sortedAgents[i];
      const nextAgent = sortedAgents[i + 1];

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

    // Update nodes and edges
    setNodes(newNodes as Node[]);
    setEdges(newEdges as Edge[]);
  }, [state, setNodes, setEdges]);

  return (
    <Card className="p-6 mb-6 overflow-hidden relative">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Crew Execution Visualization</h3>
        {state.crew?.id && (
          <Button
            variant="outline"
            size="sm"
            className="flex items-center gap-1"
            onClick={() => {
              // Use the crew ID from the state (WebSocket data) if available, otherwise fall back to the prop
              const effectiveCrewId = state.crew?.id || crewId;
              console.log(`Using crew ID for traces: ${effectiveCrewId}`);
              navigate(`/kickoff/traces?crewId=${effectiveCrewId}`);
            }}
          >
            <ExternalLink className="h-4 w-4" />
            View Traces
          </Button>
        )}
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
