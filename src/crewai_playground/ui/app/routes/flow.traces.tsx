import React, { useState, useEffect, useMemo } from "react";
import { useSearchParams, useNavigate } from "react-router";
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
  ArrowLeft,
  Moon,
  Sun,
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
      if (span.children && Array.isArray(span.children) && span.children.length > 0) {
        flattenSpans(span.children, level + 1, result);
      }
    }
  });
  return result;
};

// Helper function to format timestamp
function formatTime(timestamp: string | number) {
  try {
    const date = typeof timestamp === 'number' 
      ? new Date(timestamp / 1000) 
      : new Date(timestamp);
    return date.toLocaleString();
  } catch (e) {
    return "Invalid time";
  }
}

// Helper function to calculate duration between two timestamps
function calculateDuration(startTime: string | number, endTime?: string | number) {
  try {
    const start = typeof startTime === 'number' 
      ? new Date(startTime / 1000) 
      : new Date(startTime);
    
    if (!endTime) {
      return "In progress";
    }
    
    const end = typeof endTime === 'number' 
      ? new Date(endTime / 1000) 
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
// Main Component
// ============================================================================

// Convert TraceSpan to TimelineSpan for visualization
const convertToTimelineSpans = (spans: TraceSpan[]): TimelineSpan[] => {
  if (!spans || !Array.isArray(spans)) return [];
  
  return spans.map(span => {
    // Convert timestamp strings or numbers to Date objects
    const startTime = typeof span.start_time === 'number' 
      ? new Date(span.start_time) 
      : new Date(span.start_time);
    
    const endTime = span.end_time 
      ? typeof span.end_time === 'number'
        ? new Date(span.end_time)
        : new Date(span.end_time)
      : null;
    
    // Calculate duration in milliseconds
    const duration = endTime && startTime 
      ? endTime.getTime() - startTime.getTime() 
      : 0;
    
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
};

// Convert TraceSpan to SpanData for detail view
const convertToSpanData = (span: TraceSpan) => {
  const startTime = typeof span.start_time === 'number' 
    ? new Date(span.start_time) 
    : new Date(span.start_time);
  
  const endTime = span.end_time 
    ? typeof span.end_time === 'number'
      ? new Date(span.end_time)
      : new Date(span.end_time)
    : null;
  
  const duration = endTime && startTime 
    ? endTime.getTime() - startTime.getTime() 
    : 0;
  
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
    logs: span.events ? span.events.map(event => ({
      timestamp: typeof event.timestamp === 'number' 
        ? new Date(event.timestamp) 
        : new Date(event.timestamp),
      fields: event.attributes || {}
    })) : []
  };
};

export default function FlowTraces() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { flows, setFlows, isDarkMode, toggleDarkMode } = useChatStore();
  const [loading, setLoading] = useState(false);
  const [selectedFlowId, setSelectedFlowId] = useState<string>("");
  const [traces, setTraces] = useState<FlowTrace[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [selectedSpanId, setSelectedSpanId] = useState<string>("");

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
  const rawSelectedSpan = useMemo(() => {
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

    const spans = selectedTrace.spans || [];
    return Array.isArray(spans) ? findSpan(spans) : null;
  }, [selectedSpanId, selectedTrace]);
  
  // Convert raw span to SpanData format for detail component
  const selectedSpan = useMemo(() => {
    return rawSelectedSpan ? convertToSpanData(rawSelectedSpan) : null;
  }, [rawSelectedSpan]);

  // Process trace data for timeline view with safety checks
  const timelineSpans = useMemo(() => {
    if (!selectedTrace) return [];

    // Handle case where spans might be undefined or not an array
    const spans = selectedTrace.spans || [];
    return Array.isArray(spans) ? convertToTimelineSpans(spans) : [];
  }, [selectedTrace]);

  // Process trace data for hierarchical view with safety checks
  const hierarchicalSpans = useMemo(() => {
    if (!selectedTrace || !selectedTrace.spans) return [];

    // Create a hierarchical structure from flat spans
    const rootSpans = selectedTrace.spans.filter(
      (span) => !span.parent_id || span.parent_id === selectedTrace.id
    );
    return convertToTimelineSpans(rootSpans);
  }, [selectedTrace]);

  // Handle back button click
  const handleBack = () => {
    navigate("/flow");
  };

  return (
    <div className="flex h-screen bg-secondary/40">
      {/* Sidebar */}
      <aside className="w-80 flex flex-col border-r bg-background">
        <div className="p-4 border-b">
          <div className="flex items-center justify-between">
            <Button variant="ghost" size="icon" onClick={handleBack}>
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <h1 className="text-xl font-bold">Flow Traces</h1>
            <Button variant="ghost" size="icon" onClick={toggleDarkMode}>
              {isDarkMode ? (
                <Sun className="h-5 w-5" />
              ) : (
                <Moon className="h-5 w-5" />
              )}
            </Button>
          </div>
        </div>

        <div className="p-4 space-y-4">
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

          <Select
            onValueChange={setSelectedTraceId}
            value={selectedTraceId}
            disabled={!selectedFlowId || traces.length === 0}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select a trace" />
            </SelectTrigger>
            <SelectContent>
              {traces.map((trace) => (
                <SelectItem key={trace.id} value={trace.id}>
                  {`Trace ${trace.id.slice(0, 7)} - ${new Date(
                    trace.start_time * 1000
                  ).toLocaleString()}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {selectedTrace && (
          <div className="flex-1 overflow-y-auto p-4 border-t">
            <Card>
              <CardHeader>
                <CardTitle>Trace Details</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Status</span>
                    <Badge
                      variant={
                        selectedTrace.status === "completed"
                          ? "default"
                          : selectedTrace.status === "failed"
                          ? "destructive"
                          : "secondary"
                      }
                    >
                      {selectedTrace.status}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Start Time</span>
                    <span>{formatTime(selectedTrace.start_time)}</span>
                  </div>
                  {selectedTrace.end_time && (
                    <div className="flex items-center justify-between">
                      <span className="font-medium">End Time</span>
                      <span>{formatTime(selectedTrace.end_time)}</span>
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Duration</span>
                    <span>
                      {calculateDuration(
                        selectedTrace.start_time,
                        selectedTrace.end_time
                      )}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto p-6 bg-background">
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {loading && (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}

        {!loading && !error && !selectedTrace && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md">
              <h2 className="text-2xl font-bold mb-2">Flow Traces</h2>
              <p className="text-muted-foreground mb-4">
                Select a flow and a trace from the sidebar to view execution
                details.
              </p>
            </div>
          </div>
        )}

        {selectedTrace && (
          <div className="space-y-4">
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

                  {selectedSpan && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-lg">Span Details</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {selectedSpan && <TraceSpanDetail span={selectedSpan} />}
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
                              {selectedTrace.spans?.filter(s => s.parent_id === selectedTrace.id).length || 0}
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
                          ?.filter(method => method.parent_id === selectedTrace.id)
                          .map((method) => (
                            <AccordionItem key={method.id} value={method.id}>
                              <AccordionTrigger className="hover:bg-muted px-4">
                                <div className="flex items-center justify-between w-full">
                                  <div className="flex items-center">
                                    <Badge
                                      className={getStatusColor(method.status)}
                                      variant="outline"
                                    >
                                      {method.status}
                                    </Badge>
                                    <span className="ml-2 font-medium">{method.name}</span>
                                  </div>
                                  <div className="text-sm text-muted-foreground">
                                    {calculateDuration(method.start_time, method.end_time)}
                                  </div>
                                </div>
                              </AccordionTrigger>
                              <AccordionContent className="px-4 py-2 space-y-4">
                                <div className="grid grid-cols-2 gap-2">
                                  <div className="text-sm text-muted-foreground">Method ID</div>
                                  <div className="text-sm font-mono">{method.id}</div>

                                  <div className="text-sm text-muted-foreground">Start Time</div>
                                  <div>{formatTime(method.start_time)}</div>

                                  {method.end_time && (
                                    <>
                                      <div className="text-sm text-muted-foreground">End Time</div>
                                      <div>{formatTime(method.end_time)}</div>
                                    </>
                                  )}
                                </div>

                                {method.attributes && Object.keys(method.attributes).length > 0 && (
                                  <div className="mt-4">
                                    <div className="text-sm font-medium mb-2">Attributes</div>
                                    <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-[200px]">
                                      {JSON.stringify(method.attributes, null, 2)}
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
                          ?.flatMap(span => span.events || [])
                          .map((event, idx) => (
                            <div key={idx} className="p-3 hover:bg-muted">
                              <div className="flex justify-between items-center">
                                <Badge variant="outline">{event.name}</Badge>
                                <span className="text-xs text-muted-foreground">
                                  {formatTime(event.timestamp)}
                                </span>
                              </div>
                              {event.attributes && Object.keys(event.attributes).length > 0 && (
                                <div className="mt-2 text-xs font-mono bg-muted p-2 rounded">
                                  {JSON.stringify(event.attributes, null, 2)}
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
          </div>
        )}
      </main>
    </div>
  );
}
