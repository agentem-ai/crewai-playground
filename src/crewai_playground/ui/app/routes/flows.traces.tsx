import React, { useState, useEffect, useMemo, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router";
import { Layout } from "../components/Layout";
import { FlowNavigation } from "../components/FlowNavigation";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "../components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui/tabs";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../components/ui/sheet";
import { Badge } from "../components/ui/badge";
import {
  Loader2,
  ChevronRight,
  ChevronDown,
  Clock,
  List,
  BarChart2,
  Info,
  CheckCircle,
  XCircle,
  Play,
  Timer,
  Brain,
  Wrench,
} from "lucide-react";
import { Button } from "../components/ui/button";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "../components/ui/accordion";
import { useChatStore } from "../lib/store";
import { TraceTimeline } from "../components/TraceTimeline";
import { TraceSpanView } from "../components/TraceSpanView";
import { TraceSpanDetail } from "../components/TraceSpanDetail";
import { Separator } from "../components/ui/separator";
import { ScrollArea } from "../components/ui/scroll-area";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";

export function meta() {
  return [
    { title: "CrewAI - Flow Traces" },
    {
      name: "description",
      content: "View execution traces for flows",
    },
  ];
}

// Define trace data types based on new backend payload
interface FlowMethodEvent {
  type: string;
  timestamp: string;
  flow_id: string;
  method_name: string;
  status: string;
  input_state?: any;
  params?: any;
  outputs?: any;
  error?: string;
}

interface FlowMethod {
  name: string;
  status: string;
  start_time: string;
  end_time?: string;
  events: FlowMethodEvent[];
  outputs?: any;
}

interface FlowTrace {
  id: string;
  flow_id: string;
  flow_name: string;
  start_time: string;
  end_time?: string;
  status: string;
  events: FlowMethodEvent[];
  methods: Record<string, FlowMethod>;
  steps: any[];
  output?: string;
}

interface FlowTelemetryMetrics {
  totalMethods: number;
  totalEvents: number;
  executionTime: number;
  completedMethods: number;
  failedMethods: number;
  totalOutputSize: number;
}

interface FlowTracesResponse {
  status: string;
  traces: FlowTrace[];
}

// Legacy trace types for backward compatibility (renamed to avoid conflicts)
interface LegacyTraceSpan {
  id: string;
  name: string;
  start_time: number;
  end_time?: number;
  status: "running" | "completed" | "failed" | "initializing";
  parent_id?: string;
  attributes?: Record<string, any>;
  events?: {
    name: string;
    timestamp: number;
    attributes?: Record<string, any>;
  }[];
  children?: LegacyTraceSpan[];
  level?: number; // For flattened view
}

interface LegacyFlowTrace {
  id: string;
  flow_id: string;
  flow_name: string;
  start_time: number;
  end_time?: number;
  status: "running" | "completed" | "failed" | "initializing";
  spans: LegacyTraceSpan[];
}

// Visualization data types
interface TimelineSpan {
  id: string;
  name: string;
  startTime: Date;
  endTime: Date | null;
  status: string;
  parentId?: string;
  children: TimelineSpan[];
  depth: number;
  duration: number;
  serviceName?: string;
  operation?: string;
}

// ============================================================================
// Helper Functions
// ============================================================================

// Helper function to format timestamp
const formatTime = (timestamp: string): string => {
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      fractionalSecondDigits: 3,
    });
  } catch {
    return "--:--:--";
  }
};

// Helper function to calculate duration between two timestamps
const calculateDuration = (startTime: string, endTime?: string): string => {
  try {
    const start = new Date(startTime).getTime();
    const end = endTime ? new Date(endTime).getTime() : Date.now();
    const durationMs = end - start;

    if (durationMs < 1000) {
      return `${durationMs}ms`;
    } else if (durationMs < 60000) {
      return `${(durationMs / 1000).toFixed(1)}s`;
    } else {
      const minutes = Math.floor(durationMs / 60000);
      const seconds = Math.floor((durationMs % 60000) / 1000);
      return `${minutes}m ${seconds}s`;
    }
  } catch {
    return "--";
  }
};

// Get status color based on status
const getStatusColor = (status: string): string => {
  switch (status.toLowerCase()) {
    case "completed":
    case "success":
      return "bg-green-100 text-green-800";
    case "failed":
    case "error":
      return "bg-red-100 text-red-800";
    case "running":
    case "started":
      return "bg-blue-100 text-blue-800";
    case "initializing":
    case "pending":
      return "bg-yellow-100 text-yellow-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
};

// Get status icon based on status
const getStatusIcon = (status: string) => {
  switch (status.toLowerCase()) {
    case "completed":
    case "success":
      return <CheckCircle className="h-4 w-4" />;
    case "failed":
    case "error":
      return <XCircle className="h-4 w-4" />;
    case "running":
    case "started":
      return <Play className="h-4 w-4" />;
    case "initializing":
    case "pending":
      return <Clock className="h-4 w-4" />;
    default:
      return <Info className="h-4 w-4" />;
  }
};

// Extract telemetry metrics from trace
function extractTelemetryMetrics(trace: FlowTrace): FlowTelemetryMetrics {
  const totalMethods = Object.keys(trace.methods || {}).length;
  const totalEvents = trace.events?.length || 0;

  const startTime = new Date(trace.start_time).getTime();
  const endTime = trace.end_time
    ? new Date(trace.end_time).getTime()
    : Date.now();
  const executionTime = endTime - startTime;

  const completedMethods = Object.values(trace.methods || {}).filter(
    (method) => method.status === "completed"
  ).length;

  const failedMethods = Object.values(trace.methods || {}).filter(
    (method) => method.status === "failed"
  ).length;

  const totalOutputSize = Object.values(trace.methods || {}).reduce(
    (total, method) => {
      return (
        total + (method.outputs ? JSON.stringify(method.outputs).length : 0)
      );
    },
    0
  );

  return {
    totalMethods,
    totalEvents,
    executionTime,
    completedMethods,
    failedMethods,
    totalOutputSize,
  };
}

export default function FlowTraces() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { flows, setFlows } = useChatStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFlowId, setSelectedFlowId] = useState<string>("");
  const [traces, setTraces] = useState<FlowTrace[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [selectedSpan, setSelectedSpan] = useState<TimelineSpan | null>(null);
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedTraceDetails, setSelectedTraceDetails] =
    useState<FlowTrace | null>(null);
  const [expandedFlows, setExpandedFlows] = useState<Set<string>>(new Set());

  // Ref for span details card to enable smooth scrolling
  const spanDetailsRef = useRef<HTMLDivElement>(null);

  // Get selected trace from traces array with safety checks
  const selectedTrace = useMemo(() => {
    if (!selectedTraceId || !Array.isArray(traces)) return null;
    return (
      traces.find((trace) => trace && trace.id === selectedTraceId) || null
    );
  }, [traces, selectedTraceId]);

  // Initialize from URL params
  useEffect(() => {
    const flowId = searchParams.get("flowId");
    const traceId = searchParams.get("traceId");

    if (flowId) {
      setSelectedFlowId(flowId);
    }

    if (traceId) {
      setSelectedTraceId(traceId);
    }
  }, [searchParams]);

  // Update URL params when selections change
  useEffect(() => {
    const newParams = new URLSearchParams();
    if (selectedFlowId) {
      newParams.set("flowId", selectedFlowId);
    }
    if (selectedTraceId) {
      newParams.set("traceId", selectedTraceId);
    }
    setSearchParams(newParams);
  }, [selectedFlowId, selectedTraceId, setSearchParams]);

  // Fetch available flows on component mount
  useEffect(() => {
    const fetchFlows = async () => {
      try {
        const response = await fetch("/api/flows");
        const data = await response.json();
        if (data.flows) {
          setFlows(data.flows);

          // If no flow is selected but we have flows, select the first one
          if (data.flows.length > 0 && !selectedFlowId) {
            setSelectedFlowId(data.flows[0].id);
          }
        }
      } catch (error) {
        console.error("Error fetching flows:", error);
        setError("Failed to fetch flows. Please try again later.");
      } finally {
        setLoading(false);
      }
    };

    if (!flows.length) {
      setLoading(true);
      fetchFlows();
    } else if (!selectedFlowId && flows.length > 0) {
      // If flows are already loaded but no flow is selected, select the first one
      setSelectedFlowId(flows[0].id);
    }
  }, [flows, setFlows, selectedFlowId]);

  // Check for flowId in URL query params on initial load
  useEffect(() => {
    const flowIdFromUrl = searchParams.get("flowId");
    if (flowIdFromUrl && !selectedFlowId) {
      setSelectedFlowId(flowIdFromUrl);
    }
  }, [searchParams, selectedFlowId]);

  // Fetch traces when a flow is selected
  useEffect(() => {
    const fetchTraces = async () => {
      if (!selectedFlowId) {
        setTraces([]);
        setSelectedTraceId("");
        return;
      }

      try {
        setLoading(true);
        setError(null);

        // Update URL with the selected flow ID
        if (searchParams.get("flowId") !== selectedFlowId) {
          setSearchParams({ flowId: selectedFlowId });
        }

        const response = await fetch(`/api/flows/${selectedFlowId}/traces`);
        const data = await response.json();

        if (data.status === "success" && Array.isArray(data.traces)) {
          console.log("Received traces:", data.traces);

          // Filter out incomplete trace entries (those without proper data)
          const validTraces = data.traces.filter(
            (trace: any) =>
              trace &&
              typeof trace === "object" &&
              trace.id &&
              trace.start_time !== undefined &&
              (trace.status === "completed" ||
                trace.status === "failed" ||
                trace.status === "running" ||
                trace.status === "initializing")
          );

          // Sort traces by start_time (newest first)
          validTraces.sort((a: any, b: any) => {
            const timeA = typeof a.start_time === "number" ? a.start_time : 0;
            const timeB = typeof b.start_time === "number" ? b.start_time : 0;
            return timeB - timeA;
          });

          console.log("Valid traces after filtering:", validTraces);
          setTraces(validTraces);

          // Select the first trace if none is selected
          if (validTraces.length > 0 && !selectedTraceId) {
            setSelectedTraceId(validTraces[0].id);
          } else if (validTraces.length === 0) {
            setSelectedTraceId("");
          }
        } else {
          setError(data.detail || "Failed to fetch flow traces");
          setTraces([]);
          setSelectedTraceId("");
        }
      } catch (error) {
        console.error("Error fetching flow traces:", error);
        setError("Failed to fetch flow traces. Please try again later.");
        setTraces([]);
        setSelectedTraceId("");
      } finally {
        setLoading(false);
      }
    };

    fetchTraces();
  }, [selectedFlowId]);

  // Get telemetry metrics for the selected trace
  const telemetryMetrics = useMemo(() => {
    if (!selectedTrace) return null;
    return extractTelemetryMetrics(selectedTrace);
  }, [selectedTrace]);

  // Create timeline spans from flow trace data
  const timelineSpans = useMemo((): TimelineSpan[] => {
    if (!selectedTrace) return [];

    const spans: TimelineSpan[] = [];

    // Create flow span (root)
    const flowStartTime = new Date(selectedTrace.start_time);
    const flowEndTime = selectedTrace.end_time
      ? new Date(selectedTrace.end_time)
      : null;
    const flowDuration = flowEndTime
      ? flowEndTime.getTime() - flowStartTime.getTime()
      : 0;

    const flowSpan: TimelineSpan = {
      id: selectedTrace.id,
      name: `Flow: ${selectedTrace.flow_name}`,
      startTime: flowStartTime,
      endTime: flowEndTime,
      status: selectedTrace.status,
      depth: 0,
      duration: flowDuration,
      serviceName: "flow",
      operation: "execution",
      children: [],
    };
    spans.push(flowSpan);

    // Extract method execution data from events (similar to how crews extracts agent data)
    if (selectedTrace.events && selectedTrace.events.length > 0) {
      // Group events by method to reconstruct method execution spans
      const methodExecutions = new Map<
        string,
        {
          name: string;
          startTime: Date | null;
          endTime: Date | null;
          status: string;
          events: any[];
        }
      >();

      // Process events to extract method execution information
      selectedTrace.events.forEach((event) => {
        if (event.type === "flow.method.execution") {
          const methodName = event.method_name || "unknown_method";

          if (!methodExecutions.has(methodName)) {
            methodExecutions.set(methodName, {
              name: methodName,
              startTime: null,
              endTime: null,
              status: "unknown",
              events: [],
            });
          }

          const methodData = methodExecutions.get(methodName)!;
          methodData.events.push(event);

          const eventTime = new Date(event.timestamp);

          if (event.status === "started") {
            methodData.startTime = eventTime;
            methodData.status = "running";
          } else if (
            event.status === "completed" ||
            event.status === "failed"
          ) {
            methodData.endTime = eventTime;
            methodData.status = event.status;
          }
        }
      });

      // Create method spans from extracted data
      methodExecutions.forEach((methodData, methodName) => {
        const methodStartTime = methodData.startTime || flowStartTime;
        const methodEndTime = methodData.endTime || null;
        const methodDuration = methodEndTime
          ? methodEndTime.getTime() - methodStartTime.getTime()
          : 0;

        const methodSpan: TimelineSpan = {
          id: `${selectedTrace.id}-method-${methodName}`,
          name: `Method: ${methodData.name}`,
          startTime: methodStartTime,
          endTime: methodEndTime,
          status: methodData.status,
          parentId: selectedTrace.id,
          depth: 1,
          duration: methodDuration,
          serviceName: "method",
          operation: methodData.name,
          children: [],
        };
        spans.push(methodSpan);
      });
    }

    // Build parent-child relationships
    const spanMap = new Map<string, TimelineSpan>();
    spans.forEach((span) => spanMap.set(span.id, span));

    spans.forEach((span) => {
      if (span.parentId && spanMap.has(span.parentId)) {
        const parent = spanMap.get(span.parentId)!;
        parent.children.push(span);
      }
    });

    return spans;
  }, [selectedTrace]);

  // Handle span selection from timeline
  const handleSpanClick = (span: TimelineSpan) => {
    setSelectedSpan(span);
    setSelectedSpanId(span.id);

    // Smooth scroll to span details card after a brief delay to ensure rendering
    setTimeout(() => {
      if (spanDetailsRef.current) {
        spanDetailsRef.current.scrollIntoView({
          behavior: "smooth",
          block: "start",
          inline: "nearest",
        });
      }
    }, 100);
  };

  // Handle trace selection for drawer
  const handleTraceSelect = (trace: FlowTrace) => {
    setSelectedTraceDetails(trace);
    setSelectedTraceId(trace.id);
    setSelectedSpan(null);
    setSelectedSpanId(null);
    setDrawerOpen(true);
  };

  // Toggle flow expansion
  const toggleFlowExpansion = (flowId: string) => {
    const newExpanded = new Set(expandedFlows);
    if (newExpanded.has(flowId)) {
      newExpanded.delete(flowId);
    } else {
      newExpanded.add(flowId);
    }
    setExpandedFlows(newExpanded);
  };

  // Group traces by flow
  const groupedTraces = useMemo(() => {
    const groups = new Map<string, { flow: any; traces: FlowTrace[] }>();

    flows.forEach((flow) => {
      groups.set(flow.id, { flow, traces: [] });
    });

    traces.forEach((trace) => {
      const group = groups.get(trace.flow_id);
      if (group) {
        group.traces.push(trace);
      }
    });

    return Array.from(groups.entries())
      .filter(([_, group]) => group.traces.length > 0)
      .map(([flowId, group]) => ({ flowId, ...group }));
  }, [flows, traces]);

  // Get telemetry metrics for selected trace (for drawer)
  const selectedTraceMetrics = useMemo(() => {
    return selectedTraceDetails
      ? extractTelemetryMetrics(selectedTraceDetails)
      : null;
  }, [selectedTraceDetails]);

  return (
    <Layout>
      <div className="w-full">
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Navigation Menu */}
        <FlowNavigation />

        {/* Loading State */}
        {loading ? (
          <Card className="mb-6">
            <CardContent className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mr-2" />
              <p>Loading flow traces...</p>
            </CardContent>
          </Card>
        ) : groupedTraces.length === 0 ? (
          <Card className="mb-6">
            <CardContent className="py-12">
              <div className="text-center">
                <List className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                <h3 className="text-lg font-medium mb-2">
                  No Flow Traces Found
                </h3>
                <p className="text-gray-500 mb-4">
                  There are no execution traces available for flows yet.
                </p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-6">
            {/* Flow Traces List */}
            <Card>
              <CardHeader className="flex flex-row justify-between items-start">
                <div>
                  <CardTitle>Flow Execution Traces</CardTitle>
                  <CardDescription>
                    Click a trace to view detailed execution information
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {groupedTraces.map(({ flowId, flow, traces }) => (
                    <div key={flowId} className="space-y-2">
                      <div className="flex items-center justify-between">
                        <h4 className="font-semibold text-lg">{flow.name}</h4>
                        <Badge variant="outline" className="text-xs">
                          {traces.length} trace{traces.length !== 1 ? "s" : ""}
                        </Badge>
                      </div>
                      <div className="space-y-2">
                        {traces.map((trace) => (
                          <div
                            key={trace.id}
                            className="border rounded-lg overflow-hidden hover:bg-muted/10 transition-all cursor-pointer w-full"
                            onClick={() => handleTraceSelect(trace)}
                          >
                            <div className="p-4">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                {/* Left section - Status and details */}
                                <div className="flex items-center space-x-4">
                                  {getStatusIcon(trace.status)}
                                  <div>
                                    <div className="flex items-center">
                                      <span className="font-medium mr-2">
                                        Trace {trace.id.slice(0, 8)}
                                      </span>
                                      <Badge
                                        variant={
                                          trace.status === "completed"
                                            ? "outline"
                                            : trace.status === "running"
                                            ? "default"
                                            : "destructive"
                                        }
                                        className={
                                          trace.status === "completed"
                                            ? "bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-300"
                                            : ""
                                        }
                                      >
                                        {trace.status}
                                      </Badge>
                                    </div>
                                    <div className="text-sm text-muted-foreground mt-1">
                                      {formatTime(trace.start_time)} •{" "}
                                      {calculateDuration(
                                        trace.start_time,
                                        trace.end_time
                                      )}
                                    </div>
                                  </div>
                                </div>

                                {/* Right section - Methods and events count */}
                                <div className="flex items-center space-x-6">
                                  <div className="flex items-center space-x-2">
                                    <span className="text-sm text-muted-foreground whitespace-nowrap">
                                      Methods:
                                    </span>
                                    <span className="font-bold">
                                      {Object.keys(trace.methods || {}).length}
                                    </span>
                                  </div>

                                  <div className="flex items-center space-x-2">
                                    <span className="text-sm text-muted-foreground whitespace-nowrap">
                                      Events:
                                    </span>
                                    <span className="font-bold">
                                      {trace.events?.length || 0}
                                    </span>
                                  </div>

                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="ml-2"
                                  >
                                    <ChevronRight className="h-5 w-5" />
                                  </Button>
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Trace Details Drawer */}
        <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
          <SheetContent className="w-[75vw] max-w-[75vw] sm:w-[75vw] md:w-[75vw] lg:w-[75vw] overflow-y-auto">
            <SheetHeader>
              <SheetTitle>
                {selectedTraceDetails?.flow_name || "Flow Trace Details"}
              </SheetTitle>
              <SheetDescription>
                Detailed execution information for trace{" "}
                {selectedTraceDetails?.id?.slice(0, 8)}
              </SheetDescription>
            </SheetHeader>

            {selectedTraceDetails && (
              <div className="mt-6">
                <Tabs
                  defaultValue="overview"
                  value={activeTab}
                  onValueChange={setActiveTab}
                  className="w-full"
                >
                  <TabsList className="grid grid-cols-3 mb-4">
                    <TabsTrigger
                      value="overview"
                      className="flex items-center gap-1"
                    >
                      <Info className="h-4 w-4" />
                      <span>Overview</span>
                    </TabsTrigger>
                    <TabsTrigger
                      value="methods"
                      className="flex items-center gap-1"
                    >
                      <Play className="h-4 w-4" />
                      <span>Methods</span>
                    </TabsTrigger>
                    <TabsTrigger
                      value="events"
                      className="flex items-center gap-1"
                    >
                      <Clock className="h-4 w-4" />
                      <span>Events</span>
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="overview">
                    <div className="space-y-6">
                      {/* Telemetry Metrics */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <Card>
                          <CardContent className="p-4">
                            <div className="flex items-center space-x-2">
                              <Play className="h-5 w-5 text-blue-600" />
                              <div>
                                <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                                  Methods
                                </p>
                                <p className="text-2xl font-bold">
                                  {selectedTraceMetrics?.totalMethods || 0}
                                </p>
                                <p className="text-xs text-gray-500">
                                  {selectedTraceMetrics?.completedMethods || 0}{" "}
                                  completed,{" "}
                                  {selectedTraceMetrics?.failedMethods || 0}{" "}
                                  failed
                                </p>
                              </div>
                            </div>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardContent className="p-4">
                            <div className="flex items-center space-x-2">
                              <Clock className="h-5 w-5 text-green-600" />
                              <div>
                                <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                                  Events
                                </p>
                                <p className="text-2xl font-bold">
                                  {selectedTraceMetrics?.totalEvents || 0}
                                </p>
                                <p className="text-xs text-gray-500">
                                  Total events captured
                                </p>
                              </div>
                            </div>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardContent className="p-4">
                            <div className="flex items-center space-x-2">
                              <Timer className="h-5 w-5 text-orange-600" />
                              <div>
                                <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                                  Execution Time
                                </p>
                                <p className="text-2xl font-bold">
                                  {selectedTraceMetrics?.executionTime
                                    ? `${Math.round(
                                        selectedTraceMetrics.executionTime /
                                          1000
                                      )}s`
                                    : "0s"}
                                </p>
                                <p className="text-xs text-gray-500">
                                  Total duration
                                </p>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      </div>
                      {/* Flow Summary */}
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-lg">
                            Flow Summary
                          </CardTitle>
                          <CardDescription>
                            Overview of flow execution and status
                          </CardDescription>
                        </CardHeader>
                        <CardContent>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="space-y-2">
                              <div className="text-sm font-medium">
                                Flow Name
                              </div>
                              <div className="text-sm font-mono">
                                {selectedTraceDetails.flow_name}
                              </div>
                            </div>

                            <div className="space-y-2">
                              <div className="text-sm font-medium">Status</div>
                              <Badge
                                className={getStatusColor(
                                  selectedTraceDetails.status
                                )}
                                variant="outline"
                              >
                                {getStatusIcon(selectedTraceDetails.status)}
                                {selectedTraceDetails.status}
                              </Badge>
                            </div>

                            <div className="space-y-2">
                              <div className="text-sm font-medium">
                                Duration
                              </div>
                              <div className="text-sm">
                                {calculateDuration(
                                  selectedTraceDetails.start_time,
                                  selectedTraceDetails.end_time
                                )}
                              </div>
                            </div>
                          </div>

                          {selectedTraceDetails.output && (
                            <div className="mt-4">
                              <div className="text-sm font-medium mb-2">
                                Output
                              </div>
                              <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-[400px] whitespace-pre-wrap break-words">
                                {typeof selectedTraceDetails.output === "string"
                                  ? selectedTraceDetails.output
                                  : JSON.stringify(
                                      selectedTraceDetails.output,
                                      null,
                                      2
                                    )}
                              </pre>
                            </div>
                          )}
                        </CardContent>
                      </Card>
                      {/* Timeline Section */}
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-lg">
                            Execution Timeline
                          </CardTitle>
                          <CardDescription>
                            Visualization of execution spans over time
                          </CardDescription>
                        </CardHeader>
                        <CardContent>
                          <TraceTimeline
                            spans={timelineSpans}
                            onSpanClick={handleSpanClick}
                          />
                        </CardContent>
                      </Card>
                      {/* Span Details */}
                      {selectedSpan && (
                        <Card ref={spanDetailsRef}>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-lg">
                              Span Details
                            </CardTitle>
                            <CardDescription>
                              Detailed information for the selected span:{" "}
                              {selectedSpan.name}
                            </CardDescription>
                          </CardHeader>
                          <CardContent>
                            <TraceSpanDetail span={selectedSpan} />
                          </CardContent>
                        </Card>
                      )}
                    </div>
                  </TabsContent>

                  <TabsContent value="methods">
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-lg">Methods</CardTitle>
                        <CardDescription>
                          Flow execution methods and their details
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-4">
                          <Accordion
                            type="single"
                            collapsible
                            className="w-full"
                          >
                            {Object.entries(selectedTraceDetails.methods || {})
                              .map(([methodKey, method]) => ({
                                ...method,
                                id: methodKey,
                                name: method.name || methodKey,
                              }))
                              .map((method) => (
                                <AccordionItem
                                  key={method.id}
                                  value={method.id}
                                >
                                  <AccordionTrigger className="hover:bg-muted px-4">
                                    <div className="flex items-center justify-between w-full">
                                      <div className="flex items-center">
                                        <Badge
                                          className={getStatusColor(
                                            method.status
                                          )}
                                          variant="outline"
                                        >
                                          {getStatusIcon(method.status)}
                                          {method.status}
                                        </Badge>
                                        <span className="ml-3 font-medium">
                                          {method.name}
                                        </span>
                                      </div>
                                      <div className="text-sm text-muted-foreground mr-4">
                                        {calculateDuration(
                                          method.start_time,
                                          method.end_time
                                        )}
                                      </div>
                                    </div>
                                  </AccordionTrigger>
                                  <AccordionContent className="px-4 pb-4">
                                    <div className="space-y-4">
                                      <div className="grid grid-cols-2 gap-4 text-sm">
                                        <div>
                                          <span className="font-medium">
                                            Started:
                                          </span>
                                          <br />
                                          {formatTime(method.start_time)}
                                        </div>
                                        {method.end_time && (
                                          <div>
                                            <span className="font-medium">
                                              Completed:
                                            </span>
                                            <br />
                                            {formatTime(method.end_time)}
                                          </div>
                                        )}
                                      </div>

                                      {method.outputs && (
                                        <div>
                                          <div className="font-medium mb-2">
                                            Outputs:
                                          </div>
                                          <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-[200px] whitespace-pre-wrap break-words">
                                            {typeof method.outputs === "string"
                                              ? method.outputs
                                              : JSON.stringify(
                                                  method.outputs,
                                                  null,
                                                  2
                                                )}
                                          </pre>
                                        </div>
                                      )}
                                    </div>
                                  </AccordionContent>
                                </AccordionItem>
                              ))}
                          </Accordion>
                        </div>
                      </CardContent>
                    </Card>
                  </TabsContent>

                  <TabsContent value="events">
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-lg">Events</CardTitle>
                        <CardDescription>
                          Chronological list of all flow execution events
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <ScrollArea className="h-[600px]">
                          <div className="space-y-3">
                            {selectedTraceDetails.events &&
                              selectedTraceDetails.events
                                .sort(
                                  (a, b) =>
                                    new Date(a.timestamp).getTime() -
                                    new Date(b.timestamp).getTime()
                                )
                                .map((event, index) => {
                                  const eventIcon = getStatusIcon(event.status);
                                  const eventColor = getStatusColor(
                                    event.status
                                  );

                                  return (
                                    <div
                                      key={index}
                                      className="border rounded-lg p-4 hover:bg-muted/10 transition-colors"
                                    >
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center space-x-3">
                                          <div className={`${eventColor}`}>
                                            {eventIcon}
                                          </div>
                                          <div>
                                            <div className="flex items-center space-x-2">
                                              <span className="font-medium">
                                                {event.type}
                                              </span>
                                              <Badge variant="outline">
                                                {event.method_name || "N/A"}
                                              </Badge>
                                            </div>
                                            <div className="text-sm text-muted-foreground mt-1">
                                              Status: {event.status}
                                            </div>
                                          </div>
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                          {formatTime(event.timestamp)}
                                        </div>
                                      </div>

                                      {(event.outputs ||
                                        event.params ||
                                        event.input_state ||
                                        event.error) && (
                                        <details className="mt-3">
                                          <summary className="text-sm font-medium cursor-pointer hover:text-primary">
                                            View Event Data
                                          </summary>
                                          <div className="mt-2 text-xs font-mono bg-background/50 p-2 rounded border">
                                            {JSON.stringify(
                                              {
                                                ...(event.outputs && {
                                                  outputs: event.outputs,
                                                }),
                                                ...(event.params && {
                                                  params: event.params,
                                                }),
                                                ...(event.input_state && {
                                                  input_state:
                                                    event.input_state,
                                                }),
                                                ...(event.error && {
                                                  error: event.error,
                                                }),
                                              },
                                              null,
                                              2
                                            )}
                                          </div>
                                        </details>
                                      )}
                                    </div>
                                  );
                                })}
                          </div>
                        </ScrollArea>
                      </CardContent>
                    </Card>
                  </TabsContent>
                </Tabs>
              </div>
            )}
          </SheetContent>
        </Sheet>
      </div>
    </Layout>
  );
}
