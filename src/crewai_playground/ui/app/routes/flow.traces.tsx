import { useState, useEffect, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Button } from "~/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { useChatStore } from "~/lib/store";
import { ArrowLeft, Loader2, Moon, Sun } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import { ScrollArea } from "~/components/ui/scroll-area";
import { Badge } from "~/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";

export function meta() {
  return [
    { title: "CrewAI - Flow Traces" },
    {
      name: "description",
      content: "View execution traces for flows",
    },
  ];
}

interface TraceSpan {
  id: string;
  name: string;
  start_time: number;
  end_time?: number;
  status: "running" | "completed" | "failed" | "initializing";
  parent_id?: string;
  attributes?: Record<string, any>;
  events?: TraceEvent[];
  children?: TraceSpan[];
  level?: number; // For flattened view
}

interface TraceEvent {
  name: string;
  timestamp: number;
  attributes?: Record<string, any>;
}

interface FlowTrace {
  id: string;
  flow_id: string;
  flow_name: string;
  start_time: number;
  end_time?: number;
  status: "running" | "completed" | "failed" | "initializing";
  spans?: TraceSpan[];
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
const formatTime = (timestamp: number) => {
  if (!timestamp) return "Unknown";
  return new Date(timestamp * 1000).toLocaleTimeString();
};

// Helper function to format duration
const formatDuration = (start: number, end?: number) => {
  if (!start || !end) return "In progress";
  const duration = end - start;
  if (duration < 1) return `${(duration * 1000).toFixed(0)}ms`;
  return `${duration.toFixed(2)}s`;
};

// Helper function to get status color
const getStatusColor = (status: string) => {
  switch (status) {
    case "running":
      return "bg-blue-500";
    case "completed":
      return "bg-green-500";
    case "failed":
      return "bg-red-500";
    case "initializing":
      return "bg-yellow-500";
    default:
      return "bg-gray-500";
  }
};

// ============================================================================
// SpanHierarchy Component for Hierarchical View
// ============================================================================

interface SpanHierarchyProps {
  spans: TraceSpan[];
  selectedSpanId: string;
  onSpanClick: (id: string) => void;
  level?: number;
}

function SpanHierarchy({ spans, selectedSpanId, onSpanClick, level = 0 }: SpanHierarchyProps) {
  return (
    <div className="space-y-1">
      {spans.map((span) => (
        <div key={span.id}>
          <div
            className={`p-2 border rounded-md cursor-pointer hover:bg-muted/50 ${
              span.id === selectedSpanId ? 'bg-amber-400/20 border-amber-500' : ''
            }`}
            style={{
              marginLeft: `${level * 24}px`,
              borderLeftWidth: '4px',
              borderLeftColor:
                span.id === selectedSpanId
                  ? '#fbbf24'
                  : span.status === 'completed'
                  ? '#4caf50'
                  : span.status === 'failed'
                  ? '#f44336'
                  : '#2196f3',
            }}
            onClick={() => onSpanClick(span.id)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <div
                  className={`w-2 h-2 rounded-full mr-2 ${getStatusColor(
                    span.status
                  )}`}
                ></div>
                <span className="font-medium text-sm">{span.name}</span>
              </div>
              <Badge
                variant={
                  span.status === 'running'
                    ? 'secondary'
                    : span.status === 'completed'
                    ? 'default'
                    : span.status === 'failed'
                    ? 'destructive'
                    : 'outline'
                }
                className="text-xs"
              >
                {span.status}
              </Badge>
            </div>
          </div>
          {span.children && span.children.length > 0 && (
            <SpanHierarchy
              spans={span.children}
              selectedSpanId={selectedSpanId}
              onSpanClick={onSpanClick}
              level={level + 1}
            />
          )}
        </div>
      ))}
    </div>
  );
}


export default function FlowTraces() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { flows, setFlows, isDarkMode, toggleDarkMode } = useChatStore();
  const [loading, setLoading] = useState(false);
  const [selectedFlowId, setSelectedFlowId] = useState<string>("");
  const [traces, setTraces] = useState<FlowTrace[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>("timeline");
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
  const selectedSpan = useMemo(() => {
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

  // Process trace data for timeline view with safety checks
  const timelineSpans = useMemo(() => {
    if (!selectedTrace) return [];

    // Handle case where spans might be undefined or not an array
    const spans = selectedTrace.spans || [];
    return Array.isArray(spans) ? flattenSpans(spans) : [];
  }, [selectedTrace, flattenSpans]);

  // Process trace data for hierarchical view with safety checks
  const hierarchicalSpans = useMemo(() => {
    if (!selectedTrace || !selectedTrace.spans) return [];
    return Array.isArray(selectedTrace.spans) ? selectedTrace.spans : [];
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
                      {formatDuration(
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
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="timeline">Timeline</TabsTrigger>
                <TabsTrigger value="hierarchy">Hierarchy</TabsTrigger>
              </TabsList>
              <TabsContent value="timeline" className="mt-4">
                <ScrollArea className="h-[calc(100vh-200px)]">
                  <div className="space-y-2">
                    {timelineSpans.map((span) => (
                      <div
                        key={span.id}
                        className="p-3 border rounded-md cursor-pointer hover:bg-muted/50"
                        onClick={() => setSelectedSpanId(span.id)}
                        style={{
                          marginLeft: `${span.level * 24}px`,
                          borderLeftWidth: "4px",
                          borderLeftColor:
                            span.id === selectedSpanId
                              ? "#fbbf24"
                              : span.status === "completed"
                              ? "#4caf50"
                              : span.status === "failed"
                              ? "#f44336"
                              : "#2196f3",
                        }}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center">
                            <div
                              className={`w-3 h-3 rounded-full mr-2 ${getStatusColor(
                                span.status
                              )}`}
                            ></div>
                            <span className="font-medium">{span.name}</span>
                          </div>
                          <Badge
                            variant={
                              span.status === "running"
                                ? "secondary"
                                : span.status === "completed"
                                ? "default"
                                : span.status === "failed"
                                ? "destructive"
                                : "outline"
                            }
                          >
                            {span.status}
                          </Badge>
                        </div>

                        <div className="mt-2 text-xs text-muted-foreground">
                          <div>Start: {formatTime(span.start_time)}</div>
                          {span.end_time && (
                            <div>End: {formatTime(span.end_time)}</div>
                          )}
                          <div>
                            Duration:{" "}
                            {formatDuration(span.start_time, span.end_time)}
                          </div>
                        </div>

                        {span.id === selectedSpanId && selectedSpan && (
                          <div className="mt-2">
                            {selectedSpan.attributes &&
                              Object.keys(selectedSpan.attributes).length >
                                0 && (
                                <details className="text-xs" open>
                                  <summary className="font-medium cursor-pointer">
                                    Attributes
                                  </summary>
                                  <pre className="mt-1 p-2 bg-muted rounded-md overflow-auto max-h-[200px] whitespace-pre-wrap">
                                    {JSON.stringify(
                                      selectedSpan.attributes,
                                      null,
                                      2
                                    )}
                                  </pre>
                                </details>
                              )}
                            {selectedSpan.events &&
                              selectedSpan.events.length > 0 && (
                                <details className="text-xs mt-2" open>
                                  <summary className="font-medium cursor-pointer">
                                    Events
                                  </summary>
                                  <div className="mt-1 space-y-1">
                                    {selectedSpan.events.map((event, i) => (
                                      <div
                                        key={i}
                                        className="p-2 bg-muted/50 rounded-md"
                                      >
                                        <p className="font-medium">
                                          {event.name}
                                        </p>
                                        <p className="text-muted-foreground text-xs">
                                          {formatTime(event.timestamp)}
                                        </p>
                                        {event.attributes && (
                                          <pre className="mt-1 p-1 bg-background rounded text-xs whitespace-pre-wrap">
                                            {JSON.stringify(
                                              event.attributes,
                                              null,
                                              2
                                            )}
                                          </pre>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </details>
                              )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </TabsContent>
              <TabsContent value="hierarchy" className="mt-4">
                <ScrollArea className="h-[calc(100vh-200px)]">
                  <SpanHierarchy
                    spans={hierarchicalSpans}
                    selectedSpanId={selectedSpanId}
                    onSpanClick={setSelectedSpanId}
                  />
                </ScrollArea>
              </TabsContent>
            </Tabs>
          </div>
        )}
      </main>
    </div>
  );
}
