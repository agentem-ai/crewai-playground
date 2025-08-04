import React, { useState, useEffect, useMemo } from "react";
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
import { Badge } from "../components/ui/badge";
import {
  Loader2,
  ChevronRight,
  ChevronDown,
  Clock,
  List,
  BarChart2,
  Info,
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

// Define trace data types
interface TraceEvent {
  type: string;
  timestamp: string;
  data: Record<string, any>;
}

interface TraceMethod {
  id: string;
  name: string;
  status: string;
  start_time: string;
  end_time?: string;
  output?: string;
  events: TraceEvent[];
}

interface Trace {
  id: string;
  flow_id: string;
  flow_name: string;
  start_time: string;
  end_time?: string;
  status: string;
  output?: string;
  events: TraceEvent[];
  methods: Record<string, TraceMethod>;
}

// Original trace types for backward compatibility
interface TraceSpan {
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
  children?: TraceSpan[];
  level?: number; // For flattened view
}

interface FlowTrace {
  id: string;
  flow_id: string;
  flow_name: string;
  start_time: number;
  end_time?: number;
  status: "running" | "completed" | "failed" | "initializing";
  spans: TraceSpan[];
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

// Helper function to flatten spans into a single array with level information
const flattenSpans = (
  spans: TraceSpan[],
  level = 0,
  result: Array<TraceSpan & { level: number }> = []
) => {
  if (!spans || !Array.isArray(spans)) return result;

  spans.forEach((span) => {
    if (span) {
      result.push({ ...span, level });
      if (
        span.children &&
        Array.isArray(span.children) &&
        span.children.length > 0
      ) {
        flattenSpans(span.children, level + 1, result);
      }
    }
  });
  return result;
};

// Helper function to format timestamp
function formatTime(timestamp: string | number) {
  try {
    const date =
      typeof timestamp === "number"
        ? new Date(timestamp * 1000)
        : new Date(timestamp);
    return date.toLocaleString();
  } catch (e) {
    return "Invalid time";
  }
}

// Helper function to calculate duration between two timestamps
function calculateDuration(
  startTime: string | number,
  endTime?: string | number
) {
  try {
    const start =
      typeof startTime === "number"
        ? new Date(startTime * 1000)
        : new Date(startTime);

    if (!endTime) {
      return "In progress";
    }

    const end =
      typeof endTime === "number"
        ? new Date(endTime * 1000)
        : new Date(endTime);

    const durationMs = end.getTime() - start.getTime();
    const seconds = Math.floor((durationMs / 1000) % 60);
    const minutes = Math.floor((durationMs / (1000 * 60)) % 60);
    const hours = Math.floor(durationMs / (1000 * 60 * 60));

    if (hours > 0) {
      return `${hours}h ${minutes}m ${seconds}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    } else {
      return `${seconds}s`;
    }
  } catch (e) {
    return "Invalid time";
  }
}

// Get status color based on status
function getStatusColor(status: string) {
  switch (status.toLowerCase()) {
    case "running":
    case "initializing":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-300 border-blue-200 dark:border-blue-800";
    case "completed":
      return "bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-300 border-green-200 dark:border-green-800";
    case "failed":
      return "bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-300 border-red-200 dark:border-red-800";
    case "pending":
      return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800";
    default:
      return "bg-gray-100 text-gray-800 dark:bg-gray-900/20 dark:text-gray-300 border-gray-200 dark:border-gray-800";
  }
}

// ============================================================================
// Telemetry Conversion Functions
// ============================================================================

// Convert new telemetry format to spans for backward compatibility
function convertTelemetryToSpans(trace: any): TraceSpan[] {
  if (!trace) return [];

  try {
    // If trace already has spans (old format), use them
    if (trace.spans && Array.isArray(trace.spans)) {
      return trace.spans;
    }

    // Convert new telemetry format to spans
    const spans: TraceSpan[] = [];

    // Convert methods to spans
    if (trace.methods && typeof trace.methods === "object") {
      Object.values(trace.methods).forEach((method: any) => {
        if (method && method.id && method.name && method.start_time) {
          try {
            const span: TraceSpan = {
              id: method.id,
              name: method.name,
              start_time: new Date(method.start_time).getTime(),
              end_time: method.end_time
                ? new Date(method.end_time).getTime()
                : undefined,
              status: method.status as any,
              attributes: {
                method_name: method.name,
                outputs: method.outputs,
                error: method.error,
              },
              events: Array.isArray(method.events) ? method.events : [],
            };
            spans.push(span);
          } catch (error) {
            console.warn("Error converting method to span:", method, error);
          }
        }
      });
    }

    // If no methods, create a single span from the trace itself
    if (spans.length === 0 && trace.start_time) {
      try {
        spans.push({
          id: trace.id || "trace-root",
          name: trace.flow_name || "Flow Execution",
          start_time: new Date(trace.start_time).getTime(),
          end_time: trace.end_time
            ? new Date(trace.end_time).getTime()
            : undefined,
          status: trace.status as any,
          attributes: {
            flow_name: trace.flow_name,
            output: trace.output,
          },
          events: Array.isArray(trace.events) ? trace.events : [],
        });
      } catch (error) {
        console.warn("Error converting trace to span:", trace, error);
      }
    }

    return spans;
  } catch (error) {
    console.error("Error in convertTelemetryToSpans:", error);
    return [];
  }
}

// ============================================================================
// Main Component
// ============================================================================

// Convert TraceSpan to TimelineSpan for visualization
function convertToTimelineSpans(spans: TraceSpan[]): TimelineSpan[] {
  if (!spans || !Array.isArray(spans)) return [];

  return spans.map((span) => {
    // Convert timestamp strings or numbers to Date objects
    const startTime =
      typeof span.start_time === "number"
        ? new Date(span.start_time * 1000) // convert seconds to ms
        : new Date(span.start_time);

    const endTime = span.end_time
      ? typeof span.end_time === "number"
        ? new Date(span.end_time * 1000) // convert seconds to ms
        : new Date(span.end_time)
      : null;

    // Calculate duration in milliseconds
    const duration =
      endTime && startTime ? endTime.getTime() - startTime.getTime() : 0;

    return {
      id: span.id,
      name: span.name,
      startTime,
      endTime,
      status: span.status,
      parentId: span.parent_id,
      children: span.children ? convertToTimelineSpans(span.children) : [],
      depth: 0, // Will be calculated by TraceTimeline
      duration,
      serviceName: span.attributes?.service_name,
      operation: span.attributes?.operation,
    };
  });
}

// Convert raw span to TimelineSpan format
const convertToTimelineSpan = (span: TraceSpan): TimelineSpan => {
  const startTime =
    typeof span.start_time === "number"
      ? new Date(span.start_time * 1000)
      : new Date(span.start_time);

  const endTime = span.end_time
    ? typeof span.end_time === "number"
      ? new Date(span.end_time * 1000)
      : new Date(span.end_time)
    : null;

  return {
    id: span.id,
    name: span.name,
    startTime,
    endTime,
    status: span.status,
    parentId: span.parent_id,
    children: span.children ? convertToTimelineSpans(span.children) : [],
    depth: 0, // Will be calculated by TraceTimeline
    duration:
      endTime && startTime ? endTime.getTime() - startTime.getTime() : 0,
    serviceName: span.attributes?.service_name,
    operation: span.attributes?.operation,
  };
};

// Convert TraceSpan to SpanData for detail view
const convertToSpanData = (span: TraceSpan) => {
  const startTime =
    typeof span.start_time === "number"
      ? new Date(span.start_time * 1000)
      : new Date(span.start_time);

  const endTime = span.end_time
    ? typeof span.end_time === "number"
      ? new Date(span.end_time * 1000)
      : new Date(span.end_time)
    : null;

  const duration =
    endTime && startTime ? endTime.getTime() - startTime.getTime() : 0;

  return {
    id: span.id,
    name: span.name,
    startTime,
    endTime,
    status: span.status,
    duration,
    parentId: span.parent_id,
    depth: 0,
    tags: span.attributes || {},
    logs: span.events
      ? span.events.map((event) => ({
          timestamp:
            typeof event.timestamp === "number"
              ? new Date(event.timestamp)
              : new Date(event.timestamp),
          fields: event.attributes || {},
        }))
      : [],
  };
};

export default function FlowTraces() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { flows, setFlows, isDarkMode } = useChatStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFlowId, setSelectedFlowId] = useState<string>("");
  const [traces, setTraces] = useState<FlowTrace[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>("overview");

  // Get selected trace from traces array with safety checks
  const selectedTrace = useMemo(() => {
    if (!selectedTraceId || !Array.isArray(traces)) return null;
    return (
      traces.find((trace) => trace && trace.id === selectedTraceId) || null
    );
  }, [traces, selectedTraceId]);

  // We'll use the rawSelectedSpan defined below instead of defining rawSelectedSpan here

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

  // Get selected span from timeline
  const rawSpan = useMemo(() => {
    if (!selectedSpanId || !selectedTrace) return null;

    const findSpan = (spans: TraceSpan[] | undefined): TraceSpan | null => {
      if (!spans || !Array.isArray(spans)) return null;

      for (const span of spans) {
        if (!span) continue;
        if (span.id === selectedSpanId) return span;
        if (
          span.children &&
          Array.isArray(span.children) &&
          span.children.length > 0
        ) {
          const found = findSpan(span.children);
          if (found) return found;
        }
      }
      return null;
    };

    // Convert telemetry format to spans
    const spans = convertTelemetryToSpans(selectedTrace);
    return Array.isArray(spans) ? findSpan(spans) : null;
  }, [selectedSpanId, selectedTrace]);

  // Convert raw span to SpanData format for detail component
  const selectedSpanData = useMemo(() => {
    return rawSpan ? convertToSpanData(rawSpan) : null;
  }, [rawSpan, convertToSpanData]);

  // Process trace data for timeline view with safety checks
  const timelineSpans = useMemo(() => {
    if (!selectedTrace) return [];

    // Convert telemetry format to spans
    const spans = convertTelemetryToSpans(selectedTrace);
    return Array.isArray(spans) ? convertToTimelineSpans(spans) : [];
  }, [selectedTrace]);

  // Process trace data for hierarchical view with safety checks
  const hierarchicalSpans = useMemo(() => {
    if (!selectedTrace) return [];

    // Convert telemetry format to spans
    const spans = convertTelemetryToSpans(selectedTrace);

    // Create a hierarchical structure from flat spans
    const rootSpans = spans.filter(
      (span) => !span.parent_id || span.parent_id === selectedTrace.id
    );
    return convertToTimelineSpans(rootSpans);
  }, [selectedTrace]);

  // Render the list of traces
  const renderTraceList = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center p-4">
          <Loader2 className="h-6 w-6 animate-spin mr-2" />
          <span>Loading traces...</span>
        </div>
      );
    }

    if (error) {
      return <div className="p-4 text-red-500">{error}</div>;
    }

    if (traces.length === 0) {
      return (
        <div className="p-4 text-gray-500 dark:text-gray-400">
          No traces found.
        </div>
      );
    }

    return (
      <div className="space-y-2">
        {traces.map((trace) => (
          <div
            key={trace.id}
            className={`p-3 border rounded-md cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 ${
              selectedTrace?.id === trace.id
                ? "border-primary bg-gray-50 dark:bg-gray-800"
                : ""
            }`}
            onClick={() => {
              setSelectedTraceId(trace.id);
              setSelectedSpanId(null); // Reset selected span when changing traces
            }}
          >
            <div className="flex justify-between items-center">
              <div className="font-medium">Trace {trace.id.slice(0, 7)}</div>
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
            <div className="flex justify-between items-center text-xs text-gray-500 dark:text-gray-400 mt-1">
              <div>{formatTime(trace.start_time)}</div>
              <div>{calculateDuration(trace.start_time, trace.end_time)}</div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  // Create right sidebar with flow selection and trace list
  const rightSidebar = (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-lg font-semibold">Flows & Traces</h3>
        <p className="text-sm text-muted-foreground">
          Select a flow and trace to view details
        </p>
      </div>

      {/* Flow selection */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Flow</label>
        <Select onValueChange={setSelectedFlowId} value={selectedFlowId}>
          <SelectTrigger>
            <SelectValue placeholder="Select a flow" />
          </SelectTrigger>
          <SelectContent>
            {flows.map((flow) => (
              <SelectItem key={flow.id} value={flow.id}>
                {flow.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Trace list */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Traces</label>
        <ScrollArea className="h-[500px] border rounded-md">
          <div className="p-4">{renderTraceList()}</div>
        </ScrollArea>
      </div>
    </div>
  );

  return (
    <Layout rightSidebar={rightSidebar}>
      <div className="w-full">
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Navigation Menu */}
        {selectedFlowId && <FlowNavigation flowId={selectedFlowId} />}

        {selectedTrace ? (
          <Card>
            <CardHeader>
              <CardTitle>{selectedTrace.flow_name}</CardTitle>
            </CardHeader>
            <CardContent>
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
                  <TabsTrigger value="methods">Methods</TabsTrigger>
                  <TabsTrigger value="events">Events</TabsTrigger>
                </TabsList>
                <TabsContent value="overview">
                  <div className="space-y-6">
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-lg">Timeline</CardTitle>
                        <CardDescription>
                          Visualization of execution spans over time
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <TraceTimeline
                          spans={timelineSpans}
                          onSpanClick={(span) => setSelectedSpanId(span.id)}
                        />
                      </CardContent>
                    </Card>

                    {selectedSpanData && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-lg">
                            Span Details
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          {selectedSpanData && (
                            <TraceSpanDetail span={selectedSpanData} />
                          )}
                        </CardContent>
                      </Card>
                    )}

                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-lg">Flow Summary</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div className="space-y-2">
                            <div className="text-sm font-medium">Methods</div>
                            <div className="flex items-center gap-2">
                              <Badge className="text-lg" variant="outline">
                                {selectedTrace.spans?.filter(
                                  (s) => s.parent_id === selectedTrace.id
                                ).length || 0}
                              </Badge>
                              <span className="text-sm text-muted-foreground">
                                Total methods
                              </span>
                            </div>
                          </div>

                          <div className="space-y-2">
                            <div className="text-sm font-medium">Status</div>
                            <Badge
                              className={getStatusColor(selectedTrace.status)}
                              variant="outline"
                            >
                              {selectedTrace.status}
                            </Badge>
                          </div>

                          <div className="space-y-2">
                            <div className="text-sm font-medium">Duration</div>
                            <div className="text-sm">
                              {calculateDuration(
                                selectedTrace.start_time,
                                selectedTrace.end_time
                              )}
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
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
                        <Accordion type="single" collapsible className="w-full">
                          {selectedTrace.spans
                            ?.filter(
                              (method) => method.parent_id === selectedTrace.id
                            )
                            .map((method) => (
                              <AccordionItem key={method.id} value={method.id}>
                                <AccordionTrigger className="hover:bg-muted px-4">
                                  <div className="flex items-center justify-between w-full">
                                    <div className="flex items-center">
                                      <Badge
                                        className={getStatusColor(
                                          method.status
                                        )}
                                        variant="outline"
                                      >
                                        {method.status}
                                      </Badge>
                                      <span className="ml-2 font-medium">
                                        {method.name}
                                      </span>
                                    </div>
                                    <div className="text-sm text-muted-foreground">
                                      {calculateDuration(
                                        method.start_time,
                                        method.end_time
                                      )}
                                    </div>
                                  </div>
                                </AccordionTrigger>
                                <AccordionContent className="px-4 py-2 space-y-4">
                                  <div className="grid grid-cols-2 gap-2">
                                    <div className="text-sm text-muted-foreground">
                                      Method ID
                                    </div>
                                    <div className="text-sm font-mono">
                                      {method.id}
                                    </div>

                                    <div className="text-sm text-muted-foreground">
                                      Start Time
                                    </div>
                                    <div>{formatTime(method.start_time)}</div>

                                    {method.end_time && (
                                      <>
                                        <div className="text-sm text-muted-foreground">
                                          End Time
                                        </div>
                                        <div>{formatTime(method.end_time)}</div>
                                      </>
                                    )}
                                  </div>

                                  {method.attributes &&
                                    Object.keys(method.attributes).length >
                                      0 && (
                                      <div className="mt-4">
                                        <div className="text-sm font-medium mb-2">
                                          Attributes
                                        </div>
                                        <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-[200px]">
                                          {JSON.stringify(
                                            method.attributes,
                                            null,
                                            2
                                          )}
                                        </pre>
                                      </div>
                                    )}
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
                        Flow execution events and their details
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-4">
                        <div className="border rounded-md divide-y">
                          {selectedTrace.spans
                            ?.flatMap((span) => span.events || [])
                            .map((event, idx) => (
                              <div key={idx} className="p-3 hover:bg-muted">
                                <div className="flex justify-between items-center">
                                  <Badge variant="outline">{event.name}</Badge>
                                  <span className="text-xs text-muted-foreground">
                                    {formatTime(event.timestamp)}
                                  </span>
                                </div>
                                {event.attributes &&
                                  Object.keys(event.attributes).length > 0 && (
                                    <div className="mt-2 text-xs font-mono bg-muted p-2 rounded">
                                      {JSON.stringify(
                                        event.attributes,
                                        null,
                                        2
                                      )}
                                    </div>
                                  )}
                              </div>
                            ))}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        ) : loading ? (
          <div className="flex justify-center items-center p-8">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        ) : (
          <div className="text-center p-8 text-gray-500">
            Select a flow and trace to view details
          </div>
        )}
      </div>
    </Layout>
  );
}
