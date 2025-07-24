import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { useNavigate } from "react-router";
import {
  ReactFlow,
  Handle,
  Position,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from "@xyflow/react";
import type { Node, Edge, NodeTypes } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./flow-animations.css";
import dagre from "@dagrejs/dagre";
import { Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert";
import { Badge } from "~/components/ui/badge";
import ReactMarkdown from "react-markdown";
import { Button } from "~/components/ui/button";
import "./flow-node.css";
import { Card } from "./ui/card";

// Initial empty arrays with proper types
const initialNodes: Node[] = [];
const initialEdges: Edge[] = [];

/**
 * Helper utilities for laying out a React Flow graph using dagre.
 */
const dagreGraph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));

// Default minimum node dimensions
const MIN_NODE_WIDTH = 180;
const MIN_NODE_HEIGHT = 80;

// Default padding to add to content size
const NODE_PADDING_X = 32; // 16px padding on each side
const NODE_PADDING_Y = 24; // 12px padding on top and bottom

/**
 * Calculate the maximum dimensions needed for all nodes
 */
function calculateMaxNodeDimensions(nodes: Node[]): {
  width: number;
  height: number;
} {
  const minWidth = 180;
  const maxWidth = 400;
  const minHeight = 80;
  const maxHeight = 400;

  let maxCalculatedWidth = minWidth;
  let maxCalculatedHeight = minHeight;

  nodes.forEach((node) => {
    let width = 220; // default width
    let height = 100; // default height

    // If node has measured dimensions, use those
    if (
      node.data?.measured &&
      typeof node.data.measured === "object" &&
      "width" in node.data.measured &&
      "height" in node.data.measured
    ) {
      const measured = node.data.measured as { width: number; height: number };
      const paddingWidth = 20;
      const paddingHeight = 10;

      if (
        typeof measured.width === "number" &&
        typeof measured.height === "number" &&
        measured.width > 0 &&
        measured.height > 0
      ) {
        width = measured.width + paddingWidth;
        height = measured.height + paddingHeight;
      }
    } else {
      // Otherwise estimate based on content
      // Adjust width based on label length
      if (node.data?.label && typeof node.data.label === "string") {
        const labelLength = node.data.label.length;
        width = Math.max(minWidth, labelLength * 12);
      }

      // Adjust height based on content
      if (node.data?.description) height += 25;
      if (node.data?.error) height += 40;
      if (node.data?.dependencies && Array.isArray(node.data.dependencies)) {
        height += 30 + node.data.dependencies.length * 20;
      }
      if (node.data?.flowMethod) height += 25;

      // If node has outputs, add more height
      if (node.data?.outputs && typeof node.data.outputs === "object") {
        const outputSize = JSON.stringify(node.data.outputs).length;
        height += Math.min(200, outputSize / 5);
      }
    }

    // Constrain to min/max values
    width = Math.max(minWidth, Math.min(maxWidth, width));
    height = Math.max(minHeight, Math.min(maxHeight, height));

    // Update maximums
    maxCalculatedWidth = Math.max(maxCalculatedWidth, width);
    maxCalculatedHeight = Math.max(maxCalculatedHeight, height);
  });

  return {
    width: maxCalculatedWidth,
    height: maxCalculatedHeight,
  };
}

/**
 * Layout nodes and edges using Dagre algorithm with uniform node sizing
 */
function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  direction: "TB" | "LR" = "TB"
): { nodes: Node[]; edges: Edge[]; fullWidth: number; fullHeight: number } {
  if (nodes.length === 0) {
    return { nodes: [], edges: [], fullWidth: 0, fullHeight: 0 };
  }

  // Calculate the maximum dimensions for all nodes
  const { width: uniformWidth, height: uniformHeight } =
    calculateMaxNodeDimensions(nodes);

  // Clear the graph to avoid stale data
  dagreGraph.setGraph({});

  // Set the graph direction
  dagreGraph.setGraph({ rankdir: direction, ranksep: 100, nodesep: 80 });

  // Reset the graph before layout
  nodes.forEach((node) => {
    dagreGraph.removeNode(node.id);
  });

  // Add nodes to the graph with uniform dimensions
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: uniformWidth, height: uniformHeight });
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
        x: dagreNode.x - uniformWidth / 2,
        y: dagreNode.y - uniformHeight / 2,
      },
      // Store uniform dimensions in the node data for CSS styling
      data: {
        ...node.data,
        uniformWidth,
        uniformHeight,
      },
    };
  });

  return { nodes: layoutedNodes, edges, fullWidth, fullHeight };
}

interface FlowCanvasProps {
  flowId: string;
  isRunning: boolean;
  resetKey: number; // Key to trigger reset
}

interface FlowState {
  id: string;
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  steps: FlowStep[];
  outputs?: string | Record<string, any>;
  error?: string;
}

interface FlowStep {
  id: string;
  name: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  inputs: Record<string, any>;
  outputs: Record<string, any>;
  error?: string;
  parent_id?: string;
  dependencies?: string[];
}

/**
 * Custom hook to measure a DOM element's dimensions
 */
function useMeasureNode() {
  const ref = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState<{
    width: number;
    height: number;
  }>({ width: 0, height: 0 });

  useEffect(() => {
    // Safe update function that checks if ref is valid
    const updateMeasurements = () => {
      if (ref.current) {
        const { offsetWidth, offsetHeight } = ref.current;
        if (offsetWidth > 0 && offsetHeight > 0) {
          setDimensions({ width: offsetWidth, height: offsetHeight });
        }
      }
    };

    // Initial measurement with a small delay to ensure DOM is ready
    const initialTimer = setTimeout(updateMeasurements, 0);

    // Set up a ResizeObserver to detect content changes
    let resizeObserver: ResizeObserver | null = null;
    try {
      resizeObserver = new ResizeObserver(() => {
        if (ref.current) {
          updateMeasurements();
        }
      });

      if (ref.current) {
        resizeObserver.observe(ref.current);
      }
    } catch (error) {
      console.error("ResizeObserver error:", error);
    }

    return () => {
      clearTimeout(initialTimer);
      if (resizeObserver && ref.current) {
        try {
          resizeObserver.unobserve(ref.current);
          resizeObserver.disconnect();
        } catch (error) {
          console.error("Error cleaning up ResizeObserver:", error);
        }
      }
    };
  }, []);

  return { ref, dimensions };
}

// Custom node components with uniform sizing
const FlowNode = ({ data }: { data: any }) => {
  const { ref, dimensions } = useMeasureNode();

  // Update the node data with measured dimensions
  useEffect(() => {
    if (dimensions.width > 0 && dimensions.height > 0) {
      data.measured = dimensions;
    }
  }, [dimensions, data]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "running":
        return "bg-blue-500";
      case "completed":
        return "bg-green-500";
      case "failed":
        return "bg-red-500";
      default:
        return "bg-gray-500";
    }
  };

  // Apply uniform sizing if available
  const nodeStyle =
    data.uniformWidth && data.uniformHeight
      ? {
          width: `${data.uniformWidth}px`,
          height: `${data.uniformHeight}px`,
          minWidth: `${data.uniformWidth}px`,
          minHeight: `${data.uniformHeight}px`,
        }
      : {};

  return (
    <div
      ref={ref}
      className={`px-4 py-2 shadow-md rounded-md border bg-card flex flex-col justify-center ${
        data.uniformWidth && data.uniformHeight ? "uniform-sized" : ""
      }`}
      style={nodeStyle}
    >
      <div className="flex flex-col h-full justify-center">
        <div className="flex items-center justify-center mb-2">
          <div
            className={`w-3 h-3 rounded-full mr-2 ${getStatusColor(
              data.status
            )}`}
          ></div>
          <div className="font-bold text-lg text-center">{data.label}</div>
        </div>
        <div className="flex justify-center">
          <Badge
            variant={
              data.status === "running"
                ? "secondary"
                : data.status === "completed"
                ? "outline"
                : data.status === "failed"
                ? "destructive"
                : "outline"
            }
          >
            {data.status}
          </Badge>
        </div>
      </div>
    </div>
  );
};

const StepNode = ({ data }: { data: any }) => {
  const { ref, dimensions } = useMeasureNode();

  // Update the node data with measured dimensions
  useEffect(() => {
    if (dimensions.width > 0 && dimensions.height > 0) {
      data.measured = dimensions;
    }
  }, [dimensions, data]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "running":
        return "bg-blue-500";
      case "completed":
        return "bg-green-500";
      case "failed":
        return "bg-red-500";
      case "initializing":
        return "bg-purple-500";
      case "pending":
        return "bg-gray-500";
      default:
        return "bg-gray-500";
    }
  };

  // Apply uniform sizing if available
  const nodeStyle =
    data.uniformWidth && data.uniformHeight
      ? {
          width: `${data.uniformWidth}px`,
          height: `${data.uniformHeight}px`,
          minWidth: `${data.uniformWidth}px`,
          minHeight: `${data.uniformHeight}px`,
        }
      : {};

  return (
    <div
      ref={ref}
      className={`px-4 py-2 shadow-md rounded-md border bg-card relative overflow-hidden ${
        data.uniformWidth && data.uniformHeight ? "uniform-sized" : ""
      }`}
      style={nodeStyle}
    >
      {/* Handles for vertical flow - conditionally rendered */}
      {!data.isFirst && (
        <Handle
          type="target"
          position={Position.Top}
          className="w-2 h-2 bg-slate-500"
        />
      )}
      {!data.isLast && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="w-2 h-2 bg-slate-500"
        />
      )}

      <div className="flex flex-col h-full justify-center">
        <div className="flex items-center justify-center mb-1">
          <div
            className={`w-3 h-3 rounded-full mr-2 ${getStatusColor(
              data.status
            )}`}
          ></div>
          <div className="font-bold text-center truncate">{data.label}</div>
        </div>
        {data.description && (
          <div className="mt-1 text-xs text-muted-foreground text-center truncate">
            {data.description}
          </div>
        )}
        <div className="mt-2 flex justify-center">
          <Badge
            variant={
              data.status === "running"
                ? "secondary"
                : data.status === "completed"
                ? "outline"
                : data.status === "failed"
                ? "destructive"
                : data.status === "initializing"
                ? "default"
                : "outline"
            }
            className={`${
              data.status === "completed"
                ? "bg-green-100 text-green-800 border-green-500 dark:bg-green-900/20 dark:text-green-400 dark:border-green-800"
                : ""
            } ${data.status === "running" ? "animate-pulse" : ""}`}
          >
            {data.status === "running" && <span className="mr-1">⚡</span>}
            {data.status === "completed" && <span className="mr-1">✓</span>}
            {data.status === "failed" && <span className="mr-1">✗</span>}
            {data.status}
          </Badge>
        </div>
        {data.error && (
          <div className="mt-2 p-2 bg-red-100 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-xs text-red-500 dark:text-red-400 text-center max-h-16 overflow-y-auto">
            <div className="font-semibold">Error:</div>
            <div>{data.error}</div>
          </div>
        )}
        {data.dependencies &&
          Array.isArray(data.dependencies) &&
          data.dependencies.length > 0 && (
            <div className="mt-2 text-xs text-muted-foreground">
              <div className="font-semibold text-center">Dependencies:</div>
              <div className="max-h-16 overflow-y-auto">
                {data.dependencies.map((dep: string, i: number) => (
                  <div key={i} className="ml-2 truncate">
                    {dep}
                  </div>
                ))}
              </div>
            </div>
          )}
        {data.flowMethod && (
          <div className="mt-1 text-xs text-muted-foreground text-center truncate">
            <span className="font-semibold">Method:</span> {data.flowMethod}
          </div>
        )}
      </div>
    </div>
  );
};

const OutputNode = ({ data }: { data: any }) => {
  const { ref, dimensions } = useMeasureNode();

  // Update the node data with measured dimensions
  useEffect(() => {
    if (dimensions.width > 0 && dimensions.height > 0) {
      data.measured = dimensions;
    }
  }, [dimensions, data]);

  // Apply uniform sizing if available
  const nodeStyle =
    data.uniformWidth && data.uniformHeight
      ? {
          width: `${data.uniformWidth}px`,
          height: `${data.uniformHeight}px`,
          minWidth: `${data.uniformWidth}px`,
          minHeight: `${data.uniformHeight}px`,
        }
      : {};

  return (
    <div
      ref={ref}
      className={`px-4 py-2 shadow-md rounded-md border bg-card overflow-hidden ${
        data.uniformWidth && data.uniformHeight ? "uniform-sized" : ""
      }`}
      style={nodeStyle}
    >
      <div className="flex flex-col h-full">
        <div className="font-bold mb-2 text-center">Flow Output</div>
        <div className="text-xs overflow-auto flex-1">
          {data.output ? JSON.stringify(data.output) : "No output yet"}
        </div>
      </div>
    </div>
  );
};

const MethodNode = ({ data }: { data: any }) => {
  const { ref, dimensions } = useMeasureNode();

  // Update the node data with measured dimensions
  useEffect(() => {
    if (dimensions.width > 0 && dimensions.height > 0) {
      data.measured = dimensions;
    }
  }, [dimensions, data]);

  // Apply uniform sizing if available
  const nodeStyle =
    data.uniformWidth && data.uniformHeight
      ? {
          width: `${data.uniformWidth}px`,
          height: `${data.uniformHeight}px`,
          minWidth: `${data.uniformWidth}px`,
          minHeight: `${data.uniformHeight}px`,
        }
      : {};

  return (
    <div
      ref={ref}
      className={`px-4 py-2 shadow-md rounded-md border bg-card relative overflow-hidden ${
        data.uniformWidth && data.uniformHeight ? "uniform-sized" : ""
      }`}
      style={nodeStyle}
    >
      {/* Handles for vertical flow - conditionally rendered */}
      {!data.isFirst && (
        <Handle
          type="target"
          position={Position.Top}
          className="w-2 h-2 bg-slate-500"
        />
      )}
      {!data.isLast && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="w-2 h-2 bg-slate-500"
        />
      )}

      <div className="flex flex-col h-full justify-center">
        <div className="flex items-center justify-center mb-1">
          {data.is_step && (
            <Badge variant="secondary" className="mr-2">
              Step
            </Badge>
          )}
          <div className="font-bold text-center truncate">{data.label}</div>
        </div>
        {data.description && (
          <div className="mt-1 text-xs text-muted-foreground text-center truncate">
            {data.description}
          </div>
        )}
        {data.dependencies && data.dependencies.length > 0 && (
          <div className="mt-2 text-xs">
            <div className="font-medium text-center">Dependencies:</div>
            <div className="flex flex-wrap gap-1 mt-1 justify-center max-h-16 overflow-y-auto">
              {data.dependencies.map((dep: string) => (
                <Badge key={dep} variant="outline" className="text-xs">
                  {dep}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const FlowCanvas = ({ flowId, isRunning, resetKey }: FlowCanvasProps) => {
  const navigate = useNavigate();
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [state, setState] = useState<FlowState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Layout direction state
  const [layoutDirection, setLayoutDirection] = useState<"TB" | "LR">("TB");

  // Handle refresh layout button click
  const handleRefreshLayout = useCallback(() => {
    if (nodes.length > 0) {
      // First pass: Apply layout with current measurements
      const { nodes: layoutedNodes, edges: layoutedEdges } =
        getLayoutedElements(nodes, edges, layoutDirection);
      setNodes([...layoutedNodes]);
      setEdges([...layoutedEdges]);

      // Second pass: Allow nodes to remeasure and then apply layout again
      setTimeout(() => {
        const { nodes: refinedNodes, edges: refinedEdges } =
          getLayoutedElements(layoutedNodes, layoutedEdges, layoutDirection);
        setNodes([...refinedNodes]);
        setEdges([...refinedEdges]);
      }, 100);
    }
  }, [nodes, edges, layoutDirection, setNodes, setEdges]);

  // Add a toggle button for layout direction
  const toggleLayoutDirection = useCallback(() => {
    setLayoutDirection((prev) => (prev === "TB" ? "LR" : "TB"));

    // Force layout recalculation after direction change
    setTimeout(() => handleRefreshLayout(), 100);
  }, [setLayoutDirection, handleRefreshLayout]);

  // State for initialization view
  const [flowStructure, setFlowStructure] = useState<any>(null);
  const [loadingStructure, setLoadingStructure] = useState(false);

  // Reset execution state when resetKey changes, but preserve flow structure
  useEffect(() => {
    setState(null);
    setError(null);
    // Don't clear nodes/edges or flowStructure - we want to preserve the visualization
    // The nodes and edges will be updated by the WebSocket messages during execution

    // Close existing socket if any
    if (socket) {
      socket.close();
      setSocket(null);
    }
  }, [resetKey]);

  // Fetch flow structure when flowId changes or component mounts
  useEffect(() => {
    if (!flowId) return;

    const fetchFlowStructure = async () => {
      setLoadingStructure(true);
      setError(null);

      try {
        // First check if the flow exists
        const flowsResponse = await fetch("/api/flows");
        const flowsData = await flowsResponse.json();

        if (flowsData.status === "success") {
          const flowExists = flowsData.flows.some(
            (flow: any) => flow.id === flowId
          );

          if (!flowExists) {
            setError(
              `Flow with ID ${flowId} not found. Please select a valid flow.`
            );
            setLoadingStructure(false);
            return;
          }
        }

        // Fetch the flow structure
        const response = await fetch(`/api/flows/${flowId}/structure`);

        if (!response.ok) {
          if (response.status === 404) {
            setError(
              `Flow with ID ${flowId} not found. Please select a valid flow.`
            );
          } else {
            setError(`Error fetching flow structure: ${response.statusText}`);
          }
          setLoadingStructure(false);
          return;
        }

        const data = await response.json();

        if (data.status === "success" && data.flow) {
          setFlowStructure(data.flow);
          createInitialVisualization(data.flow);
        } else {
          setError(data.detail || "Failed to fetch flow structure");
        }
      } catch (err) {
        console.error("Error fetching flow structure:", err);
        setError("Failed to fetch flow structure. Please try again.");
      } finally {
        setLoadingStructure(false);
      }
    };

    fetchFlowStructure();
  }, [flowId]);

  // Connect to WebSocket when flowId changes or isRunning becomes true
  useEffect(() => {
    if (!flowId || !isRunning) return;

    setLoading(true);
    setError(null);

    // Track connection attempts
    let connectionAttempts = 0;
    const maxConnectionAttempts = 3;
    let connectionTimer: ReturnType<typeof setTimeout> | null = null;

    // Function to create and connect WebSocket
    const connectWebSocket = () => {
      // Determine WebSocket URL based on current location
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/ws/flow/${flowId}`;

      const newSocket = new WebSocket(wsUrl);

      // Set a timeout for connection establishment
      const connectionTimeout = setTimeout(() => {
        if (newSocket.readyState !== WebSocket.OPEN) {
          console.warn("WebSocket connection timeout");
          newSocket.close();

          // Try to reconnect if we haven't exceeded max attempts
          if (connectionAttempts < maxConnectionAttempts) {
            connectionAttempts++;
            connectionTimer = setTimeout(connectWebSocket, 1000); // Wait 1 second before retry
          } else {
            setError(
              "Failed to connect to flow execution after multiple attempts. Please try again."
            );
            setLoading(false);
          }
        }
      }, 5000); // 5 second timeout

      newSocket.onopen = () => {
        clearTimeout(connectionTimeout);
        setLoading(false);
      };

      newSocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "flow_state") {
            // Deep copy to avoid state mutation issues
            setState((prevState) => {
              // If no previous state, just use the new payload
              if (!prevState) return data.payload;

              const newState = JSON.parse(JSON.stringify(prevState));

              // Update flow status
              newState.status = data.payload.status;

              // Update outputs if available
              if (data.payload.outputs) {
                newState.outputs = data.payload.outputs;
              }

              // Update steps using a Map for efficient merging
              if (data.payload.steps && Array.isArray(data.payload.steps)) {
                const stepMap = new Map(
                  newState.steps.map((s: any) => [s.id, s])
                );

                data.payload.steps.forEach((newStep: any) => {
                  stepMap.set(newStep.id, {
                    ...(stepMap.get(newStep.id) || {}),
                    ...newStep,
                  });
                });

                newState.steps = Array.from(stepMap.values());
              }

              // Update errors if any
              if (data.payload.errors && Array.isArray(data.payload.errors)) {
                newState.errors = [
                  ...(newState.errors || []),
                  ...data.payload.errors,
                ];
              }

              return newState;
            });
          } else if (data.type === "error") {
            setError(data.message || "An error occurred during flow execution");
          }
        } catch (err) {
          console.error("Error parsing WebSocket message:", err);
        }
      };

      newSocket.onerror = (event) => {
        console.error("WebSocket error:", event);
        clearTimeout(connectionTimeout);

        // Only set error if we've exhausted our retries
        if (connectionAttempts >= maxConnectionAttempts) {
          setError("Failed to connect to flow execution. Please try again.");
          setLoading(false);
        }
      };

      newSocket.onclose = (event) => {
        clearTimeout(connectionTimeout);

        // If this wasn't a normal closure and we haven't exceeded retries, try to reconnect
        if (
          event.code !== 1000 &&
          event.code !== 1001 &&
          connectionAttempts < maxConnectionAttempts
        ) {
          connectionAttempts++;
          connectionTimer = setTimeout(connectWebSocket, 1000);
        }
      };

      setSocket(newSocket);
    };

    // Start the connection process
    connectWebSocket();

    // Clean up on unmount
    return () => {
      if (socket) {
        socket.close();
      }

      // Clear any pending connection timers
      if (connectionTimer) {
        clearTimeout(connectionTimer);
      }
    };
  }, [flowId, isRunning, resetKey]);

  // Update nodes and edges based on flow state during execution
  useEffect(() => {
    if (!state) return;

    // Use callback to get current nodes and edges to avoid infinite loop
    setNodes((currentNodes) => {
      if (currentNodes.length === 0) return currentNodes;

      // Create a map of existing nodes for easy lookup
      const nodeMap = new Map(currentNodes.map((node) => [node.id, node]));

      // Update the flow node status if it exists
      const flowNodeId = `flow-${state.id}`;
      const updatedNodes = [...currentNodes];

      // Update flow node if it exists
      const flowNodeIndex = currentNodes.findIndex((n) => n.id === flowNodeId);
      if (flowNodeIndex >= 0) {
        updatedNodes[flowNodeIndex] = {
          ...currentNodes[flowNodeIndex],
          data: {
            ...currentNodes[flowNodeIndex].data,
            status: state.status,
          },
        };
      }

      // Update step nodes with their current status
      state.steps.forEach((step) => {
        const stepNodeId = `method-${step.id}`;
        const nodeIndex = currentNodes.findIndex((n) => n.id === stepNodeId);

        if (nodeIndex >= 0) {
          // Update existing node with new status and outputs
          updatedNodes[nodeIndex] = {
            ...currentNodes[nodeIndex],
            data: {
              ...currentNodes[nodeIndex].data,
              status: step.status,
              outputs: step.outputs,
              error: step.error,
            },
            className: getStatusAnimation(step.status),
          };
        }
      });

      // Output node has been removed as per user request
      // Flow results will only be displayed in the results section below the visualization

      return updatedNodes;
    });

    // Update edges separately
    setEdges((currentEdges) => {
      const updatedEdges = [...currentEdges];

      // Update edges connected to step nodes
      state.steps.forEach((step) => {
        const stepNodeId = `method-${step.id}`;

        updatedEdges.forEach((edge, index) => {
          if (edge.source === stepNodeId || edge.target === stepNodeId) {
            updatedEdges[index] = {
              ...edge,
              animated: step.status === "running",
              style: {
                ...edge.style,
                stroke: getStatusColor(step.status),
                strokeWidth: step.status === "running" ? 3 : 2,
                opacity: step.status === "pending" ? 0.6 : 1,
              },
              markerEnd: edge.markerEnd
                ? {
                    ...(edge.markerEnd as any),
                    color: getStatusColor(step.status),
                  }
                : undefined,
            };
          }
        });
      });

      // Add output edge if flow is completed and it doesn't exist yet
      if (
        state.status === "completed" &&
        state.outputs &&
        (typeof state.outputs === "string"
          ? state.outputs.trim().length > 0
          : Object.keys(state.outputs).length > 0) &&
        !currentEdges.some((e) => e.id === "flow-to-output")
      ) {
        const flowNodeId = `flow-${state.id}`;
        updatedEdges.push({
          id: "flow-to-output",
          source: flowNodeId,
          target: "output-node",
          type: "smoothstep",
          style: {
            stroke: "#4caf50",
            strokeWidth: 2,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: "#4caf50",
          },
        });
      }

      return updatedEdges;
    });
  }, [state]);

  // Track if initial layout has been applied
  const [initialLayoutApplied, setInitialLayoutApplied] = useState(false);

  // Update layout when nodes, edges, or layout direction changes
  useEffect(() => {
    // Skip layout if we have no nodes
    if (nodes.length === 0) return;

    // Skip layout recalculation if we've already applied the initial layout
    // and the node/edge count hasn't changed (just status updates)
    if (initialLayoutApplied && state?.status !== "pending") {
      return;
    }

    // Check if nodes have measured dimensions
    const hasMeasuredNodes = nodes.some(
      (node) =>
        node.data?.measured &&
        typeof node.data.measured === "object" &&
        "width" in node.data.measured &&
        "height" in node.data.measured
    );

    // Apply layout with current measurements
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      nodes,
      edges,
      layoutDirection
    );
    setNodes(layoutedNodes);
    setEdges(layoutedEdges);

    // If nodes have been measured, schedule another layout update to use the measurements
    if (hasMeasuredNodes) {
      // Use a longer timeout to ensure measurements are stable
      setTimeout(() => {
        const { nodes: refinedNodes, edges: refinedEdges } =
          getLayoutedElements(layoutedNodes, layoutedEdges, layoutDirection);
        setNodes(refinedNodes);
        setEdges(refinedEdges);
        setInitialLayoutApplied(true);
      }, 150);
    } else {
      setInitialLayoutApplied(true);
    }
  }, [nodes.length, edges.length, layoutDirection, state?.status]); // Added state?.status to detect status changes

  // Helper function to get color based on status
  const getStatusColor = (status: string) => {
    switch (status) {
      case "running":
        return "#2196f3"; // Bright Blue
      case "completed":
        return "#4caf50"; // Bright Green
      case "failed":
        return "#f44336"; // Bright Red
      case "pending":
        return "#9e9e9e"; // Gray
      case "initializing":
        return "#9c27b0"; // Purple
      default:
        return "#9e9e9e"; // Gray
    }
  };

  // Helper function to get animation class based on status
  const getStatusAnimation = (status: string) => {
    switch (status) {
      case "running":
        return "animate-pulse-subtle";
      case "initializing":
        return "animate-fade-in";
      default:
        return "";
    }
  };

  // Create initial visualization that will be updated during execution
  const createInitialVisualization = (flowData: any) => {
    if (!flowData || !flowData.methods) return;

    const newNodes: Node[] = [];
    const newEdges: Edge[] = [];

    // Root (flow) node
    const rootNode = {
      id: `flow-${flowData.id}`,
      type: "flowNode",
      position: { x: 0, y: 0 }, // Start at origin, will be repositioned
      data: {
        label: flowData.name,
        status: "pending",
        id: flowData.id,
      },
    };
    newNodes.push(rootNode);

    // Improved vertical layout variables
    const verticalGap = 200; // Increased gap between nodes
    const horizontalCenter = 0; // Center horizontally
    const startY = 150; // Distance from root node

    // First, map of methodId -> method for quick lookup
    const methodMap: Record<string, any> = {};
    flowData.methods.forEach((m: any) => {
      methodMap[m.id] = m;
    });

    // Create a topological sort to properly arrange nodes
    const visited = new Set<string>();
    const visiting = new Set<string>();
    const sortedMethods: any[] = [];

    const topologicalSort = (methodId: string) => {
      if (visiting.has(methodId)) return; // Circular dependency
      if (visited.has(methodId)) return;

      visiting.add(methodId);
      const method = methodMap[methodId];

      if (method && method.dependencies) {
        method.dependencies.forEach((depId: string) => {
          if (methodMap[depId]) {
            topologicalSort(depId);
          }
        });
      }

      visiting.delete(methodId);
      visited.add(methodId);
      if (method) {
        sortedMethods.push(method);
      }
    };

    // Sort all methods
    flowData.methods.forEach((method: any) => {
      topologicalSort(method.id);
    });

    // Add method nodes with proper vertical spacing
    sortedMethods.forEach((method: any, index: number) => {
      const nodeY = startY + index * verticalGap;
      newNodes.push({
        id: `method-${method.id}`,
        type: "methodNode",
        position: { x: horizontalCenter, y: nodeY },
        data: {
          label: method.name,
          description: method.description,
          is_step: method.is_step,
          dependencies: method.dependencies || [],
          isFirst: index === 0,
          isLast: index === sortedMethods.length - 1,
        },
      });

      // Edge from flow root to methods without dependencies
      if (!method.dependencies || method.dependencies.length === 0) {
        newEdges.push({
          id: `edge-flow-${method.id}`,
          source: `flow-${flowData.id}`,
          target: `method-${method.id}`,
          type: "smoothstep",
          markerEnd: { type: MarkerType.ArrowClosed, color: "#2196f3" },
          style: { stroke: "#2196f3", strokeWidth: 2 },
        });
      }
    });

    // Add dependency edges between method nodes
    sortedMethods.forEach((method: any) => {
      if (method.dependencies && method.dependencies.length > 0) {
        method.dependencies.forEach((depId: string) => {
          if (methodMap[depId]) {
            newEdges.push({
              id: `edge-${depId}-to-${method.id}`,
              source: `method-${depId}`,
              target: `method-${method.id}`,
              type: "smoothstep",
              markerEnd: { type: MarkerType.ArrowClosed, color: "#ff9800" },
              style: {
                stroke: "#ff9800",
                strokeWidth: 2,
                strokeDasharray: "5 5",
              },
            });
          }
        });
      }
    });

    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      newNodes,
      newEdges,
      layoutDirection
    );
    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
  };

  return (
    <Card className="p-6 mb-6 overflow-hidden">
      <div className="p-4 flex justify-between items-center flex-shrink-0">
        <h3 className="font-semibold text-lg">Flow Visualization</h3>
      </div>
      {(loading || loadingStructure) && (
        <div className="absolute inset-0 flex items-center justify-center z-10 bg-background/80">
          <div className="text-center">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2 text-primary" />
            <p className="text-sm text-muted-foreground">
              {loading
                ? "Connecting to flow execution..."
                : "Loading flow structure..."}
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="p-4">
          <Alert>
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </div>
      )}

      {!flowStructure &&
        nodes.length === 0 &&
        !loading &&
        !loadingStructure &&
        !error && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md">
              <h3 className="text-lg font-medium mb-2">Flow Visualization</h3>
              <p className="text-sm text-muted-foreground">
                Select a flow to visualize its structure.
              </p>
            </div>
          </div>
        )}

      <div className="h-[600px] border rounded-md overflow-hidden mb-6">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{
            padding: 0.2, // Add padding around the view
            includeHiddenNodes: false,
            minZoom: 0.1, // Allow zooming out more
            maxZoom: 1.5,
          }}
          minZoom={0.1}
          maxZoom={2}
          defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>

      {/* Flow Results Section */}
      {state?.status === "completed" &&
        state?.outputs &&
        (typeof state.outputs === "string"
          ? state.outputs.trim().length > 0
          : Object.keys(state.outputs).length > 0) && (
          <div className="mt-4">
            <h3 className="text-lg font-semibold mb-4">Flow Results</h3>
            <div className="p-6 rounded-lg border bg-card overflow-auto">
              <div className="text-base leading-7">
                {typeof state.outputs === "string" ? (
                  <ReactMarkdown
                    components={{
                      h1: ({ ...props }) => (
                        <h1
                          className="text-2xl font-bold mt-6 mb-4"
                          {...props}
                        />
                      ),
                      h2: ({ ...props }) => (
                        <h2
                          className="text-xl font-bold mt-5 mb-3"
                          {...props}
                        />
                      ),
                      h3: ({ ...props }) => (
                        <h3
                          className="text-lg font-bold mt-4 mb-2"
                          {...props}
                        />
                      ),
                      p: ({ ...props }) => <p className="mb-4" {...props} />,
                      ul: ({ ...props }) => (
                        <ul className="list-disc pl-6 mb-4" {...props} />
                      ),
                      ol: ({ ...props }) => (
                        <ol className="list-decimal pl-6 mb-4" {...props} />
                      ),
                      li: ({ ...props }) => <li className="mb-1" {...props} />,
                      a: ({ ...props }) => (
                        <a
                          className="text-blue-500 hover:underline"
                          {...props}
                        />
                      ),
                      blockquote: ({ ...props }) => (
                        <blockquote
                          className="border-l-4 border-muted pl-4 italic my-4"
                          {...props}
                        />
                      ),
                      code: ({ children, className, ...props }: any) => {
                        const match = /language-(\w+)/.exec(className || "");
                        const isInline =
                          !match && !children?.toString().includes("\n");
                        return isInline ? (
                          <code
                            className="bg-muted px-1 py-0.5 rounded"
                            {...props}
                          >
                            {children}
                          </code>
                        ) : (
                          <pre className="bg-muted p-4 rounded-md overflow-x-auto mb-4">
                            <code className={className} {...props}>
                              {children}
                            </code>
                          </pre>
                        );
                      },
                    }}
                  >
                    {state.outputs}
                  </ReactMarkdown>
                ) : (
                  <div className="space-y-4">
                    {Object.entries(state.outputs).map(([key, value]) => (
                      <div
                        key={key}
                        className="border-b border-muted pb-4 last:border-b-0"
                      >
                        <h4 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground mb-2">
                          {key}
                        </h4>
                        <div className="text-sm">
                          {typeof value === "string" ? (
                            <ReactMarkdown
                              components={{
                                p: ({ ...props }) => (
                                  <p className="mb-2" {...props} />
                                ),
                                code: ({
                                  children,
                                  className,
                                  ...props
                                }: any) => {
                                  const match = /language-(\w+)/.exec(
                                    className || ""
                                  );
                                  const isInline =
                                    !match &&
                                    !children?.toString().includes("\n");
                                  return isInline ? (
                                    <code
                                      className="bg-muted px-1 py-0.5 rounded"
                                      {...props}
                                    >
                                      {children}
                                    </code>
                                  ) : (
                                    <pre className="bg-muted p-2 rounded-md overflow-x-auto mb-2">
                                      <code className={className} {...props}>
                                        {children}
                                      </code>
                                    </pre>
                                  );
                                },
                              }}
                            >
                              {value}
                            </ReactMarkdown>
                          ) : (
                            <pre className="bg-muted p-2 rounded-md overflow-x-auto text-xs">
                              {JSON.stringify(value, null, 2)}
                            </pre>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
    </Card>
  );
};

// Define node types after the component definitions
const nodeTypes: NodeTypes = {
  flowNode: FlowNode,
  stepNode: StepNode,
  outputNode: OutputNode,
  methodNode: MethodNode,
};

export default FlowCanvas;
