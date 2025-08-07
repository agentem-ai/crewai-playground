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
const extractTelemetryMetrics = (trace: FlowTrace) => {
  const methods = Object.values(trace.methods || {});
  const totalMethods = methods.length;
  const completedMethods = methods.filter(
    (m) => m.status === "completed"
  ).length;
  const failedMethods = methods.filter((m) => m.status === "failed").length;

  const totalDuration =
    trace.end_time && trace.start_time
      ? new Date(trace.end_time).getTime() -
        new Date(trace.start_time).getTime()
      : 0;

  return {
    totalMethods,
    completedMethods,
    failedMethods,
    totalDuration,
    successRate: totalMethods > 0 ? (completedMethods / totalMethods) * 100 : 0,
  };
};

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
  const [activeTab, setActiveTab] = useState<string>("overview");

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
                        <CardTitle className="text-lg">Flow Summary</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div className="space-y-2">
                            <div className="text-sm font-medium">Methods</div>
                            <div className="flex items-center gap-2">
                              <Badge className="text-lg" variant="outline">
                                {telemetryMetrics?.totalMethods || 0}
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
                          {Object.entries(selectedTrace.methods || {})
                            .map(([methodKey, method]) => ({
                              ...method,
                              id: methodKey,
                              name: method.name || methodKey,
                            }))
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

                                  {method.outputs &&
                                    Object.keys(method.outputs).length > 0 && (
                                      <div className="mt-4">
                                        <div className="text-sm font-medium mb-2">
                                          Outputs
                                        </div>
                                        <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-[200px]">
                                          {JSON.stringify(
                                            method.outputs,
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
                          {selectedTrace.events?.map((event, idx) => (
                            <div key={idx} className="p-3 hover:bg-muted">
                              <div className="flex justify-between items-center">
                                <Badge variant="outline">{event.type}</Badge>
                                <span className="text-xs text-muted-foreground">
                                  {formatTime(event.timestamp)}
                                </span>
                              </div>
                              <div className="mt-2 text-sm">
                                <div>
                                  <strong>Method:</strong> {event.method_name}
                                </div>
                                <div>
                                  <strong>Status:</strong> {event.status}
                                </div>
                              </div>
                              {(event.outputs ||
                                event.params ||
                                event.input_state) && (
                                <div className="mt-2 text-xs font-mono bg-muted p-2 rounded">
                                  {JSON.stringify(
                                    {
                                      ...(event.outputs && {
                                        outputs: event.outputs,
                                      }),
                                      ...(event.params && {
                                        params: event.params,
                                      }),
                                      ...(event.input_state && {
                                        input_state: event.input_state,
                                      }),
                                      ...(event.error && {
                                        error: event.error,
                                      }),
                                    },
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
