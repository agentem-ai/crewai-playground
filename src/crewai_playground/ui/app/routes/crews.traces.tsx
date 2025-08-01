import React, { useState, useEffect, useMemo } from "react";
import { useSearchParams, useNavigate, useLocation } from "react-router";
import { Layout } from "../components/Layout";
import { KickoffNavigation } from "../components/KickoffNavigation";
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
  Info,
  ArrowLeft,
  Clock,
  Users,
  CheckCircle,
  XCircle,
  AlertCircle,
  Brain,
  Wrench,
  Zap,
  Timer,
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

// Define trace data// Type definitions
interface TraceEvent {
  type: string;
  timestamp: string;
  data: Record<string, any>;
}

interface LLMCall {
  id: string;
  type: 'llm.started' | 'llm.completed' | 'llm.failed';
  timestamp: string;
  model?: string;
  prompt?: string;
  completion?: string;
  tokens?: number;
  status: 'started' | 'completed' | 'failed';
  agent_id?: string;
  agent_name?: string;
  task_id?: string;
  error?: string;
  duration?: number;
}

interface ToolExecution {
  id: string;
  type: 'tool.started' | 'tool.completed' | 'tool.failed';
  timestamp: string;
  tool_name?: string;
  inputs?: any;
  outputs?: any;
  status: 'started' | 'completed' | 'failed';
  agent_id?: string;
  agent_name?: string;
  error?: string;
  duration?: number;
}

interface TelemetryMetrics {
  totalLLMCalls: number;
  totalToolExecutions: number;
  totalTokens: number;
  executionTime: number;
  completedLLMCalls: number;
  failedLLMCalls: number;
  completedToolExecutions: number;
  failedToolExecutions: number;
}

interface Agent {
  id: string;
  name: string;
  role: string;
  status: string;
  start_time: string;
  end_time?: string;
  llmCalls?: LLMCall[];
  toolExecutions?: ToolExecution[];
}

interface Task {
  id: string;
  description: string;
  agent_id?: string;
  status: string;
  start_time: string;
  end_time?: string;
  output?: string;
}

interface Trace {
  id: string;
  crew_id: string;
  crew_name: string;
  status: string;
  start_time: string;
  end_time?: string;
  events: TraceEvent[];
  agents: Record<string, Agent>;
  tasks: Record<string, Task>;
  telemetryMetrics?: TelemetryMetrics;
  llmCalls?: LLMCall[];
  toolExecutions?: ToolExecution[];
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

export function meta() {
  return [
    { title: "CrewAI - Execution Traces" },
    {
      name: "description",
      content: "View execution traces for your CrewAI agents",
    },
  ];
}

export default function TracesPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isDarkMode } = useChatStore();
  const [searchParams] = useSearchParams();
  const crewId = searchParams.get("crewId");

  const [traces, setTraces] = useState<Trace[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [selectedSpan, setSelectedSpan] = useState<TimelineSpan | null>(null);
  const [telemetryData, setTelemetryData] = useState<{
    llmCalls: LLMCall[];
    toolExecutions: ToolExecution[];
    metrics: TelemetryMetrics;
  } | null>(null);

  const handleBack = () => {
    navigate(`/kickoff?crewId=${crewId}`);
  };

  // Transform trace data into timeline spans
  const timelineSpans = useMemo(() => {
    if (!selectedTrace) return [];

    console.log('Creating timeline spans for trace:', {
      traceId: selectedTrace.id,
      hasLLMCalls: !!selectedTrace.llmCalls,
      llmCallsCount: selectedTrace.llmCalls?.length || 0,
      hasToolExecutions: !!selectedTrace.toolExecutions,
      toolExecutionsCount: selectedTrace.toolExecutions?.length || 0,
      agentsCount: Object.keys(selectedTrace.agents || {}).length,
      tasksCount: Object.keys(selectedTrace.tasks || {}).length
    });

    const spans: TimelineSpan[] = [];

    // Add crew span as root
    const crewStartTime = new Date(selectedTrace.start_time);
    const crewEndTime = selectedTrace.end_time
      ? new Date(selectedTrace.end_time)
      : null;
    const crewDuration = crewEndTime
      ? crewEndTime.getTime() - crewStartTime.getTime()
      : 0;

    const crewSpan: TimelineSpan = {
      id: selectedTrace.id,
      name: `Crew: ${selectedTrace.crew_name}`,
      startTime: crewStartTime,
      endTime: crewEndTime,
      status: selectedTrace.status,
      depth: 0,
      duration: crewDuration,
      serviceName: "crew",
      operation: "execution",
      children: [],
    };
    spans.push(crewSpan);

    // Add agent spans - ensure agents is an object before iterating
    if (selectedTrace.agents && typeof selectedTrace.agents === 'object') {
      Object.values(selectedTrace.agents).forEach((agent) => {
        const agentStartTime = new Date(agent.start_time);
        const agentEndTime = agent.end_time ? new Date(agent.end_time) : null;
        const agentDuration = agentEndTime
          ? agentEndTime.getTime() - agentStartTime.getTime()
          : 0;

        const agentSpan: TimelineSpan = {
          id: agent.id,
          name: `Agent: ${agent.name}`,
          startTime: agentStartTime,
          endTime: agentEndTime,
          status: agent.status,
          parentId: selectedTrace.id,
          depth: 1,
          duration: agentDuration,
          serviceName: "agent",
          operation: agent.role,
          children: [],
        };
        spans.push(agentSpan);

        // Add LLM calls as child spans of the agent
        if (agent.llmCalls && agent.llmCalls.length > 0) {
          agent.llmCalls.forEach((llmCall, index) => {
            const llmStartTime = new Date(llmCall.timestamp);
            // Estimate end time based on status and duration (if available) or use a small offset
            const llmEndTime = llmCall.duration 
              ? new Date(llmStartTime.getTime() + llmCall.duration)
              : llmCall.status === 'completed' 
                ? new Date(llmStartTime.getTime() + 2000) // 2 second default
                : null;
            
            const llmSpan: TimelineSpan = {
              id: `${agent.id}-llm-${index}`,
              name: `LLM Call: ${llmCall.model || 'Unknown Model'}`,
              startTime: llmStartTime,
              endTime: llmEndTime,
              status: llmCall.status,
              parentId: agent.id,
              depth: 2,
              duration: llmCall.duration || (llmEndTime ? llmEndTime.getTime() - llmStartTime.getTime() : 0),
              serviceName: "llm",
              operation: llmCall.type,
              children: [],
            };
            spans.push(llmSpan);
          });
        }

        // Add tool executions as child spans of the agent
        if (agent.toolExecutions && agent.toolExecutions.length > 0) {
          agent.toolExecutions.forEach((toolExec, index) => {
            const toolStartTime = new Date(toolExec.timestamp);
            // Estimate end time based on status and duration (if available) or use a small offset
            const toolEndTime = toolExec.duration 
              ? new Date(toolStartTime.getTime() + toolExec.duration)
              : toolExec.status === 'completed' 
                ? new Date(toolStartTime.getTime() + 1000) // 1 second default
                : null;
            
            const toolSpan: TimelineSpan = {
              id: `${agent.id}-tool-${index}`,
              name: `Tool: ${toolExec.tool_name || 'Unknown Tool'}`,
              startTime: toolStartTime,
              endTime: toolEndTime,
              status: toolExec.status,
              parentId: agent.id,
              depth: 2,
              duration: toolExec.duration || (toolEndTime ? toolEndTime.getTime() - toolStartTime.getTime() : 0),
              serviceName: "tool",
              operation: toolExec.type,
              children: [],
            };
            spans.push(toolSpan);
          });
        }
      });
    }

    // Add task spans - ensure tasks is an object before iterating
    if (selectedTrace.tasks && typeof selectedTrace.tasks === 'object') {
      Object.values(selectedTrace.tasks).forEach((task) => {
      const taskStartTime = new Date(task.start_time);
      const taskEndTime = task.end_time ? new Date(task.end_time) : null;
      const taskDuration = taskEndTime
        ? taskEndTime.getTime() - taskStartTime.getTime()
        : 0;

      const taskSpan: TimelineSpan = {
        id: task.id,
        name:
          task.description.length > 30
            ? `${task.description.substring(0, 30)}...`
            : task.description,
        startTime: taskStartTime,
        endTime: taskEndTime,
        status: task.status,
        parentId: task.agent_id || selectedTrace.id,
        depth: 2,
        duration: taskDuration,
        serviceName: "task",
        operation: "execution",
        children: [],
      };
      spans.push(taskSpan);
      });
    }

    // Add trace-level LLM calls and tool executions (not associated with specific agents)
    if (selectedTrace.llmCalls && selectedTrace.llmCalls.length > 0) {
      selectedTrace.llmCalls.forEach((llmCall, index) => {
        // Only add if not already associated with an agent
        if (!llmCall.agent_id) {
          const llmStartTime = new Date(llmCall.timestamp);
          const llmEndTime = llmCall.duration 
            ? new Date(llmStartTime.getTime() + llmCall.duration)
            : llmCall.status === 'completed' 
              ? new Date(llmStartTime.getTime() + 2000) // 2 second default
              : null;
          
          const llmSpan: TimelineSpan = {
            id: `crew-llm-${index}`,
            name: `LLM Call: ${llmCall.model || 'Unknown Model'}`,
            startTime: llmStartTime,
            endTime: llmEndTime,
            status: llmCall.status,
            parentId: selectedTrace.id,
            depth: 1,
            duration: llmCall.duration || (llmEndTime ? llmEndTime.getTime() - llmStartTime.getTime() : 0),
            serviceName: "llm",
            operation: llmCall.type,
            children: [],
          };
          spans.push(llmSpan);
        }
      });
    }

    if (selectedTrace.toolExecutions && selectedTrace.toolExecutions.length > 0) {
      selectedTrace.toolExecutions.forEach((toolExec, index) => {
        // Only add if not already associated with an agent
        if (!toolExec.agent_id) {
          const toolStartTime = new Date(toolExec.timestamp);
          const toolEndTime = toolExec.duration 
            ? new Date(toolStartTime.getTime() + toolExec.duration)
            : toolExec.status === 'completed' 
              ? new Date(toolStartTime.getTime() + 1000) // 1 second default
              : null;
          
          const toolSpan: TimelineSpan = {
            id: `crew-tool-${index}`,
            name: `Tool: ${toolExec.tool_name || 'Unknown Tool'}`,
            startTime: toolStartTime,
            endTime: toolEndTime,
            status: toolExec.status,
            parentId: selectedTrace.id,
            depth: 1,
            duration: toolExec.duration || (toolEndTime ? toolEndTime.getTime() - toolStartTime.getTime() : 0),
            serviceName: "tool",
            operation: toolExec.type,
            children: [],
          };
          spans.push(toolSpan);
        }
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

  // Calculate total duration for timeline
  const totalDuration = useMemo(() => {
    if (!selectedTrace) return 0;
    const startTime = new Date(selectedTrace.start_time).getTime();
    const endTime = selectedTrace.end_time
      ? new Date(selectedTrace.end_time).getTime()
      : Date.now();
    return endTime - startTime;
  }, [selectedTrace]);

  // Handle span selection
  const handleSpanClick = (span: TimelineSpan) => {
    setSelectedSpan(span);
  };

  // Render timeline visualization
  const renderTimeline = () => {
    if (!selectedTrace) return null;

    return (
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
              onSpanClick={handleSpanClick}
            />
          </CardContent>
        </Card>

        {selectedSpan && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Span Details</CardTitle>
            </CardHeader>
            <CardContent>
              <TraceSpanDetail span={selectedSpan} />
            </CardContent>
          </Card>
        )}
      </div>
    );
  };

  // Render hierarchical span view
  const renderSpans = () => {
    if (!selectedTrace) return null;

    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">Spans</CardTitle>
                <CardDescription>
                  Hierarchical view of execution spans
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[500px]">
                  <TraceSpanView
                    spans={timelineSpans}
                    totalDuration={totalDuration}
                    onSpanClick={handleSpanClick}
                  />
                </ScrollArea>
              </CardContent>
            </Card>
          </div>

          <div>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">Span Details</CardTitle>
              </CardHeader>
              <CardContent>
                <TraceSpanDetail span={selectedSpan} />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    );
  };

  // Fetch traces on component mount
  useEffect(() => {
    async function fetchTraces() {
      try {
        setLoading(true);
        const response = await fetch(`/api/crews/${crewId}/traces`);
        if (!response.ok) {
          throw new Error(`Failed to fetch traces: ${response.statusText}`);
        }
        const data = await response.json();
        
        // Process trace data and extract telemetry information
        const processedData = data.map((trace: any) => {
          const processedTrace = {
            ...trace,
            agents: trace.agents || {},
            tasks: trace.tasks || {},
            events: trace.events || []
          };
          
          // Extract telemetry data from events
          const telemetryData = extractTelemetryData(processedTrace);
          
          return {
            ...processedTrace,
            telemetryMetrics: telemetryData.metrics,
            llmCalls: telemetryData.llmCalls,
            toolExecutions: telemetryData.toolExecutions
          };
        });
        
        setTraces(processedData);
        // Select the first trace by default
        if (processedData.length > 0) {
          const firstTrace = processedData[0];
          setSelectedTrace(firstTrace);
          // Set telemetry data for the selected trace
          if (firstTrace.llmCalls && firstTrace.toolExecutions && firstTrace.telemetryMetrics) {
            setTelemetryData({
              llmCalls: firstTrace.llmCalls,
              toolExecutions: firstTrace.toolExecutions,
              metrics: firstTrace.telemetryMetrics
            });
          }
        }
      } catch (err) {
        console.error('Error fetching traces:', err);
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }

    fetchTraces();
  }, [crewId]);

  // Extract telemetry data from trace events
  const extractTelemetryData = (trace: any) => {
    const llmCalls: LLMCall[] = [];
    const toolExecutions: ToolExecution[] = [];
    const events = trace.events || [];

    // Group events by agent_id and task_id to pair started/completed events
    const llmEventGroups = new Map<string, { started?: any, completed?: any, failed?: any }>();
    const toolEventGroups = new Map<string, { started?: any, completed?: any, failed?: any }>();

    // First pass: group events by agent_id + task_id
    events.forEach((event: TraceEvent) => {
      if (event.type.startsWith('llm.')) {
        const key = `${event.data.agent_id || 'unknown'}-${event.data.task_id || 'unknown'}`;
        if (!llmEventGroups.has(key)) {
          llmEventGroups.set(key, {});
        }
        const group = llmEventGroups.get(key)!;
        if (event.type === 'llm.started') {
          group.started = event;
        } else if (event.type === 'llm.completed') {
          group.completed = event;
        } else if (event.type === 'llm.failed') {
          group.failed = event;
        }
      } else if (event.type.startsWith('tool.')) {
        const key = `${event.data.agent_id || 'unknown'}-${event.data.tool_name || 'unknown'}`;
        if (!toolEventGroups.has(key)) {
          toolEventGroups.set(key, {});
        }
        const group = toolEventGroups.get(key)!;
        if (event.type === 'tool.started') {
          group.started = event;
        } else if (event.type === 'tool.completed') {
          group.completed = event;
        } else if (event.type === 'tool.failed') {
          group.failed = event;
        }
      }
    });

    // Second pass: create LLM calls with proper duration calculation
    llmEventGroups.forEach((group, key) => {
      const startEvent = group.started;
      const endEvent = group.completed || group.failed;
      
      if (startEvent || endEvent) {
        const event = endEvent || startEvent;
        const startTime = startEvent ? new Date(startEvent.timestamp).getTime() : new Date(event.timestamp).getTime();
        const endTime = endEvent ? new Date(endEvent.timestamp).getTime() : null;
        const duration = endTime ? endTime - startTime : undefined;
        
        const llmCall: LLMCall = {
          id: event.data.id || `llm-${key}-${event.timestamp}`,
          type: endEvent ? endEvent.type as LLMCall['type'] : startEvent.type as LLMCall['type'],
          timestamp: startEvent ? startEvent.timestamp : event.timestamp,
          model: event.data.model || 'Unknown Model',
          prompt: event.data.prompt,
          completion: endEvent?.data.completion,
          tokens: endEvent?.data.tokens,
          status: group.completed ? 'completed' : group.failed ? 'failed' : 'started',
          agent_id: event.data.agent_id,
          agent_name: event.data.agent_name,
          task_id: event.data.task_id,
          error: group.failed?.data.error,
          duration
        };
        llmCalls.push(llmCall);
      }
    });

    // Second pass: create tool executions with proper duration calculation
    toolEventGroups.forEach((group, key) => {
      const startEvent = group.started;
      const endEvent = group.completed || group.failed;
      
      if (startEvent || endEvent) {
        const event = endEvent || startEvent;
        const startTime = startEvent ? new Date(startEvent.timestamp).getTime() : new Date(event.timestamp).getTime();
        const endTime = endEvent ? new Date(endEvent.timestamp).getTime() : null;
        const duration = endTime ? endTime - startTime : undefined;
        
        const toolExecution: ToolExecution = {
          id: event.data.id || `tool-${key}-${event.timestamp}`,
          type: endEvent ? endEvent.type as ToolExecution['type'] : startEvent.type as ToolExecution['type'],
          timestamp: startEvent ? startEvent.timestamp : event.timestamp,
          tool_name: event.data.tool_name || 'Unknown Tool',
          inputs: event.data.inputs,
          outputs: endEvent?.data.outputs,
          status: group.completed ? 'completed' : group.failed ? 'failed' : 'started',
          agent_id: event.data.agent_id,
          agent_name: event.data.agent_name,
          error: group.failed?.data.error,
          duration
        };
        toolExecutions.push(toolExecution);
      }
    });

    // Calculate metrics
    const totalLLMCalls = llmCalls.length;
    const completedLLMCalls = llmCalls.filter(call => call.status === 'completed').length;
    const failedLLMCalls = llmCalls.filter(call => call.status === 'failed').length;
    const totalToolExecutions = toolExecutions.length;
    const completedToolExecutions = toolExecutions.filter(exec => exec.status === 'completed').length;
    const failedToolExecutions = toolExecutions.filter(exec => exec.status === 'failed').length;
    const totalTokens = llmCalls.reduce((sum, call) => sum + (call.tokens || 0), 0);
    
    const startTime = trace.start_time ? new Date(trace.start_time).getTime() : 0;
    const endTime = trace.end_time ? new Date(trace.end_time).getTime() : Date.now();
    const executionTime = endTime - startTime;

    const metrics: TelemetryMetrics = {
      totalLLMCalls,
      totalToolExecutions,
      totalTokens,
      executionTime,
      completedLLMCalls,
      failedLLMCalls,
      completedToolExecutions,
      failedToolExecutions
    };

    // Enhance agents with their LLM calls and tool executions
    Object.values(trace.agents || {}).forEach((agent: any) => {
      agent.llmCalls = llmCalls.filter(call => call.agent_id === agent.id);
      agent.toolExecutions = toolExecutions.filter(exec => exec.agent_id === agent.id);
    });

    console.log('Extracted telemetry data:', {
      llmCallsCount: llmCalls.length,
      toolExecutionsCount: toolExecutions.length,
      llmCalls: llmCalls.map(call => ({ id: call.id, model: call.model, agent_id: call.agent_id, duration: call.duration })),
      toolExecutions: toolExecutions.map(exec => ({ id: exec.id, tool_name: exec.tool_name, agent_id: exec.agent_id, duration: exec.duration }))
    });

    return { llmCalls, toolExecutions, metrics };
  };

  // Update telemetry data when selected trace changes
  useEffect(() => {
    if (selectedTrace && selectedTrace.llmCalls && selectedTrace.toolExecutions && selectedTrace.telemetryMetrics) {
      setTelemetryData({
        llmCalls: selectedTrace.llmCalls,
        toolExecutions: selectedTrace.toolExecutions,
        metrics: selectedTrace.telemetryMetrics
      });
    } else {
      setTelemetryData(null);
    }
  }, [selectedTrace]);

  // Format timestamp to readable format
  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
  };

  // Calculate duration between two timestamps
  const calculateDuration = (startTime?: string, endTime?: string) => {
    if (!startTime || !endTime) return "N/A";

    try {
      const start = new Date(startTime).getTime();
      const end = new Date(endTime).getTime();
      const durationMs = end - start;

      // Format duration
      if (durationMs < 1000) {
        return `${durationMs}ms`;
      } else if (durationMs < 60000) {
        return `${(durationMs / 1000).toFixed(2)}s`;
      } else {
        const minutes = Math.floor(durationMs / 60000);
        const seconds = ((durationMs % 60000) / 1000).toFixed(2);
        return `${minutes}m ${seconds}s`;
      }
    } catch (e) {
      return "Invalid time";
    }
  };

  // Get status color based on status
  const getStatusColor = (status: string) => {
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
  };

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
            className={`p-4 rounded-lg cursor-pointer hover:bg-accent/50 ${
              selectedTrace?.id === trace.id
                ? "bg-accent/50 border border-accent"
                : "border"
            }`}
            onClick={() => {
              setSelectedTrace(trace);
              setSelectedSpan(null); // Reset selected span when changing traces
              // Update telemetry data for the selected trace
              if (trace.llmCalls && trace.toolExecutions && trace.telemetryMetrics) {
                setTelemetryData({
                  llmCalls: trace.llmCalls,
                  toolExecutions: trace.toolExecutions,
                  metrics: trace.telemetryMetrics
                });
              } else {
                setTelemetryData(null);
              }
            }}
          >
            <div className="flex justify-between items-center">
              <div className="font-medium">{trace.crew_name}</div>
              <Badge
                variant={
                  trace.status === "completed"
                    ? "outline"
                    : trace.status === "running"
                    ? "default"
                    : "destructive"
                }
              >
                {trace.status}
              </Badge>
            </div>
            <div className="flex justify-between items-center text-xs text-muted-foreground mt-1">
              <div>{formatTime(trace.start_time)}</div>
              <div className="flex items-center gap-2">
                <span>
                  {trace.agents && typeof trace.agents === 'object' ? Object.keys(trace.agents).length : 0} agents
                </span>
                <span>{trace.tasks && typeof trace.tasks === 'object' ? Object.keys(trace.tasks).length : 0} tasks</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  // Render overview tab with timeline
  const renderOverviewWithTimeline = () => {
    if (!selectedTrace) return null;

    const agentCount = Object.keys(selectedTrace.agents).length;
    const taskCount = Object.keys(selectedTrace.tasks).length;
    const eventCount = selectedTrace.events.length;

    const completedAgents = Object.values(selectedTrace.agents).filter(
      (agent) => agent.status === "completed"
    ).length;

    const completedTasks = Object.values(selectedTrace.tasks).filter(
      (task) => task.status === "completed"
    ).length;

    return (
      <div className="space-y-6">
        {/* Telemetry Metrics Overview */}
        {selectedTrace.telemetryMetrics && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Zap className="h-5 w-5" />
              Telemetry Metrics
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-2xl font-bold text-blue-600">{selectedTrace.telemetryMetrics.totalLLMCalls}</div>
                      <div className="text-sm text-gray-500">LLM Calls</div>
                      <div className="text-xs text-gray-400">
                        {selectedTrace.telemetryMetrics.completedLLMCalls} completed, {selectedTrace.telemetryMetrics.failedLLMCalls} failed
                      </div>
                    </div>
                    <Brain className="h-8 w-8 text-blue-500" />
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-2xl font-bold text-green-600">{selectedTrace.telemetryMetrics.totalToolExecutions}</div>
                      <div className="text-sm text-gray-500">Tool Executions</div>
                      <div className="text-xs text-gray-400">
                        {selectedTrace.telemetryMetrics.completedToolExecutions} completed, {selectedTrace.telemetryMetrics.failedToolExecutions} failed
                      </div>
                    </div>
                    <Wrench className="h-8 w-8 text-green-500" />
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-2xl font-bold text-purple-600">{selectedTrace.telemetryMetrics.totalTokens.toLocaleString()}</div>
                      <div className="text-sm text-gray-500">Total Tokens</div>
                      <div className="text-xs text-gray-400">
                        Across all LLM calls
                      </div>
                    </div>
                    <Zap className="h-8 w-8 text-purple-500" />
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-2xl font-bold text-orange-600">
                        {selectedTrace.telemetryMetrics.executionTime < 60000 
                          ? `${(selectedTrace.telemetryMetrics.executionTime / 1000).toFixed(1)}s`
                          : `${(selectedTrace.telemetryMetrics.executionTime / 60000).toFixed(1)}m`
                        }
                      </div>
                      <div className="text-sm text-gray-500">Execution Time</div>
                      <div className="text-xs text-gray-400">
                        Total duration
                      </div>
                    </div>
                    <Timer className="h-8 w-8 text-orange-500" />
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Basic Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{agentCount}</div>
              <div className="text-sm text-gray-500">
                Agents ({completedAgents} completed)
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{taskCount}</div>
              <div className="text-sm text-gray-500">
                Tasks ({completedTasks} completed)
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{eventCount}</div>
              <div className="text-sm text-gray-500">Events</div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <h3 className="text-lg font-semibold">Execution Details</h3>
          <div className="grid grid-cols-2 gap-2">
            <div className="text-sm text-gray-500">Crew ID</div>
            <div className="text-sm font-mono">{selectedTrace.crew_id}</div>

            <div className="text-sm text-gray-500">Trace ID</div>
            <div className="text-sm font-mono">{selectedTrace.id}</div>

            <div className="text-sm text-gray-500">Status</div>
            <div>
              <Badge className={getStatusColor(selectedTrace.status)}>
                {selectedTrace.status}
              </Badge>
            </div>

            <div className="text-sm text-gray-500">Start Time</div>
            <div className="text-sm">
              {formatTime(selectedTrace.start_time)}
            </div>

            {selectedTrace.end_time && (
              <>
                <div className="text-sm text-gray-500">End Time</div>
                <div className="text-sm">
                  {formatTime(selectedTrace.end_time)}
                </div>

                <div className="text-sm text-gray-500">Duration</div>
                <div className="text-sm">
                  {calculateDuration(
                    selectedTrace.start_time,
                    selectedTrace.end_time
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Timeline visualization */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Execution Timeline</CardTitle>
            <CardDescription>
              A hierarchical view of the execution spans
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TraceTimeline
              spans={timelineSpans}
              onSpanClick={handleSpanClick}
            />
          </CardContent>
        </Card>

        {selectedSpan && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Span Details</CardTitle>
              <CardDescription>
                Detailed information for the selected span: {selectedSpan.name}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <TraceSpanDetail span={selectedSpan} />
            </CardContent>
          </Card>
        )}
      </div>
    );
  };

  // Render agents tab
  const renderAgents = () => {
    if (!selectedTrace) return null;

    // Ensure agents is an object before calling Object.values
    const agents = selectedTrace.agents && typeof selectedTrace.agents === 'object' 
      ? Object.values(selectedTrace.agents) 
      : [];

    if (agents.length === 0) {
      return (
        <div className="p-4 text-gray-500 dark:text-gray-400">
          No agent data available.
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <Accordion type="single" collapsible className="w-full">
          {agents.map((agent) => (
            <AccordionItem key={agent.id} value={agent.id}>
              <AccordionTrigger className="hover:bg-gray-50 dark:hover:bg-gray-800/50 px-4">
                <div className="flex items-center justify-between w-full">
                  <div className="flex items-center">
                    <Badge
                      className={getStatusColor(agent.status)}
                      variant="outline"
                    >
                      {agent.status}
                    </Badge>
                    <span className="ml-2 font-medium">{agent.name}</span>
                    <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">
                      ({agent.role})
                    </span>
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {calculateDuration(agent.start_time, agent.end_time)}
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent className="px-4 py-2 space-y-4">
                <div className="grid grid-cols-2 gap-2">
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    Agent ID
                  </div>
                  <div className="text-sm font-mono">{agent.id}</div>

                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    Start Time
                  </div>
                  <div>{formatTime(agent.start_time)}</div>

                  {agent.end_time && (
                    <div className="grid grid-cols-2 col-span-2">
                      <div className="text-sm text-gray-500 dark:text-gray-400">
                        End Time
                      </div>
                      <div>{formatTime(agent.end_time)}</div>
                    </div>
                  )}

                  {/* LLM Calls Section */}
                  {agent.llmCalls && agent.llmCalls.length > 0 && (
                    <div className="col-span-2">
                      <div className="text-sm text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-2">
                        <Brain className="h-4 w-4" />
                        LLM Calls ({agent.llmCalls.length})
                      </div>
                      <div className="space-y-2">
                        {agent.llmCalls.map((call, idx) => (
                          <div key={idx} className="border rounded-md p-3 bg-blue-50 dark:bg-blue-900/20">
                            <div className="flex justify-between items-center mb-2">
                              <div className="flex items-center gap-2">
                                <Badge variant={call.status === 'completed' ? 'default' : call.status === 'failed' ? 'destructive' : 'secondary'}>
                                  {call.status}
                                </Badge>
                                {call.model && <span className="text-sm font-mono">{call.model}</span>}
                              </div>
                              <span className="text-xs text-gray-500">{formatTime(call.timestamp)}</span>
                            </div>
                            {call.tokens && (
                              <div className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                                <Zap className="h-3 w-3 inline mr-1" />
                                {call.tokens} tokens
                              </div>
                            )}
                            {call.prompt && (
                              <details className="mb-2">
                                <summary className="text-sm font-medium cursor-pointer hover:text-blue-600">View Prompt</summary>
                                <div className="mt-1 p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono whitespace-pre-wrap">
                                  {call.prompt.length > 500 ? `${call.prompt.substring(0, 500)}...` : call.prompt}
                                </div>
                              </details>
                            )}
                            {call.completion && (
                              <details>
                                <summary className="text-sm font-medium cursor-pointer hover:text-blue-600">View Response</summary>
                                <div className="mt-1 p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono whitespace-pre-wrap">
                                  {call.completion.length > 500 ? `${call.completion.substring(0, 500)}...` : call.completion}
                                </div>
                              </details>
                            )}
                            {call.error && (
                              <div className="text-sm text-red-600 dark:text-red-400 mt-2">
                                <AlertCircle className="h-3 w-3 inline mr-1" />
                                {call.error}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Tool Executions Section */}
                  {agent.toolExecutions && agent.toolExecutions.length > 0 && (
                    <div className="col-span-2">
                      <div className="text-sm text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-2">
                        <Wrench className="h-4 w-4" />
                        Tool Executions ({agent.toolExecutions.length})
                      </div>
                      <div className="space-y-2">
                        {agent.toolExecutions.map((execution, idx) => (
                          <div key={idx} className="border rounded-md p-3 bg-green-50 dark:bg-green-900/20">
                            <div className="flex justify-between items-center mb-2">
                              <div className="flex items-center gap-2">
                                <Badge variant={execution.status === 'completed' ? 'default' : execution.status === 'failed' ? 'destructive' : 'secondary'}>
                                  {execution.status}
                                </Badge>
                                {execution.tool_name && <span className="text-sm font-mono">{execution.tool_name}</span>}
                              </div>
                              <span className="text-xs text-gray-500">{formatTime(execution.timestamp)}</span>
                            </div>
                            {execution.inputs && (
                              <details className="mb-2">
                                <summary className="text-sm font-medium cursor-pointer hover:text-green-600">View Inputs</summary>
                                <div className="mt-1 p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono">
                                  {JSON.stringify(execution.inputs, null, 2)}
                                </div>
                              </details>
                            )}
                            {execution.outputs && (
                              <details>
                                <summary className="text-sm font-medium cursor-pointer hover:text-green-600">View Outputs</summary>
                                <div className="mt-1 p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono">
                                  {JSON.stringify(execution.outputs, null, 2)}
                                </div>
                              </details>
                            )}
                            {execution.error && (
                              <div className="text-sm text-red-600 dark:text-red-400 mt-2">
                                <AlertCircle className="h-3 w-3 inline mr-1" />
                                {execution.error}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    );
  };

  // Render tasks tab
  const renderTasks = () => {
    if (!selectedTrace) return null;

    // Ensure tasks is an object before calling Object.values
    const tasks = selectedTrace.tasks && typeof selectedTrace.tasks === 'object' 
      ? Object.values(selectedTrace.tasks) 
      : [];

    if (tasks.length === 0) {
      return (
        <div className="p-4 text-gray-500 dark:text-gray-400">
          No task data available.
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <Accordion type="single" collapsible className="w-full">
          {tasks.map((task) => (
            <AccordionItem key={task.id} value={task.id}>
              <AccordionTrigger className="hover:bg-gray-50 dark:hover:bg-gray-800/50 px-4">
                <div className="flex items-center justify-between w-full">
                  <div className="flex items-center">
                    <Badge
                      className={getStatusColor(task.status)}
                      variant="outline"
                    >
                      {task.status}
                    </Badge>
                    <span className="ml-2 font-medium truncate max-w-md">
                      {task.description}
                    </span>
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {calculateDuration(task.start_time, task.end_time)}
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent className="px-4 py-2 space-y-4">
                <div className="grid grid-cols-2 gap-2">
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    Task ID
                  </div>
                  <div className="text-sm font-mono">{task.id}</div>

                  {task.agent_id && (
                    <div className="grid grid-cols-2 gap-2">
                      <div className="text-sm text-gray-500 dark:text-gray-400">
                        Assigned Agent
                      </div>
                      <div className="text-sm font-mono">{task.agent_id}</div>
                    </div>
                  )}

                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    Start Time
                  </div>
                  <div>{formatTime(task.start_time)}</div>

                  {task.end_time && (
                    <div className="grid grid-cols-2 col-span-2">
                      <div className="text-sm text-gray-500 dark:text-gray-400">
                        End Time
                      </div>
                      <div>{formatTime(task.end_time)}</div>
                    </div>
                  )}

                  {task.output && (
                    <div className="col-span-2">
                      <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
                        Output
                      </div>
                      <div className="bg-gray-50 dark:bg-gray-800/50 p-2 rounded-md text-sm whitespace-pre-wrap font-mono">
                        {task.output}
                      </div>
                    </div>
                  )}

                  {/* Task-specific details can be added here if needed */}
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    );
  };

  // Get event type color and icon
  const getEventTypeInfo = (eventType: string) => {
    if (eventType.includes('completed')) {
      return { color: 'text-green-600', bgColor: 'bg-green-100 dark:bg-green-900/30', icon: CheckCircle };
    } else if (eventType.includes('failed') || eventType.includes('error')) {
      return { color: 'text-red-600', bgColor: 'bg-red-100 dark:bg-red-900/30', icon: XCircle };
    } else if (eventType.includes('started')) {
      return { color: 'text-blue-600', bgColor: 'bg-blue-100 dark:bg-blue-900/30', icon: Clock };
    } else if (eventType.includes('llm')) {
      return { color: 'text-purple-600', bgColor: 'bg-purple-100 dark:bg-purple-900/30', icon: Brain };
    } else if (eventType.includes('tool')) {
      return { color: 'text-orange-600', bgColor: 'bg-orange-100 dark:bg-orange-900/30', icon: Wrench };
    } else {
      return { color: 'text-gray-600', bgColor: 'bg-gray-100 dark:bg-gray-900/30', icon: Info };
    }
  };

  // Render events tab
  const renderEvents = () => {
    if (!selectedTrace) return null;
    
    // Ensure events is an array before checking length
    const events = Array.isArray(selectedTrace.events) ? selectedTrace.events : [];
    
    if (events.length === 0) {
      return (
        <div className="p-4 text-gray-500 dark:text-gray-400">
          No event data available.
        </div>
      );
    }

    // Sort events by timestamp
    const sortedEvents = [...events].sort((a, b) => 
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Events Timeline ({sortedEvents.length})
          </h3>
        </div>
        
        <ScrollArea className="h-[600px]">
          <div className="space-y-3">
            {sortedEvents.map((event, idx) => {
              const typeInfo = getEventTypeInfo(event.type);
              const IconComponent = typeInfo.icon;
              
              return (
                <div
                  key={idx}
                  className={`border rounded-lg p-4 ${typeInfo.bgColor} hover:shadow-md transition-shadow`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <IconComponent className={`h-5 w-5 ${typeInfo.color} flex-shrink-0`} />
                      <div>
                        <div className="flex items-center gap-2">
                          <Badge 
                            variant="outline" 
                            className={`${typeInfo.color} border-current`}
                          >
                            {event.type}
                          </Badge>
                          {event.data.agent_name && (
                            <span className="text-sm text-gray-600 dark:text-gray-300">
                              Agent: {event.data.agent_name}
                            </span>
                          )}
                          {event.data.task_id && (
                            <span className="text-sm text-gray-600 dark:text-gray-300">
                              Task: {event.data.task_id}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          {formatTime(event.timestamp)}
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Event-specific details */}
                  {event.data.model && (
                    <div className="mt-2 text-sm text-gray-700 dark:text-gray-300">
                      <strong>Model:</strong> {event.data.model}
                    </div>
                  )}
                  {event.data.tokens && (
                    <div className="mt-1 text-sm text-gray-700 dark:text-gray-300">
                      <strong>Tokens:</strong> {event.data.tokens}
                    </div>
                  )}
                  {event.data.tool_name && (
                    <div className="mt-1 text-sm text-gray-700 dark:text-gray-300">
                      <strong>Tool:</strong> {event.data.tool_name}
                    </div>
                  )}
                  {event.data.error && (
                    <div className="mt-2 text-sm text-red-600 dark:text-red-400">
                      <strong>Error:</strong> {event.data.error}
                    </div>
                  )}
                  
                  {/* Expandable raw data */}
                  {Object.keys(event.data).length > 0 && (
                    <details className="mt-3">
                      <summary className="text-sm font-medium cursor-pointer hover:text-blue-600 dark:hover:text-blue-400">
                        View Raw Event Data
                      </summary>
                      <div className="mt-2 text-xs font-mono bg-gray-50 dark:bg-gray-800 p-3 rounded border overflow-x-auto">
                        <pre>{JSON.stringify(event.data, null, 2)}</pre>
                      </div>
                    </details>
                  )}
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </div>
    );
  };

  // Create right sidebar with trace selection
  const rightSidebar = (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-lg font-semibold">Traces</h3>
        <p className="text-sm text-muted-foreground">Select a trace to view details</p>
      </div>
      <ScrollArea className="h-[500px] border rounded-md">
        <div className="p-4">{renderTraceList()}</div>
      </ScrollArea>
    </div>
  );

  return (
    <Layout rightSidebar={rightSidebar}>
      <div className="w-full">
        {/* Navigation Menu */}
        <KickoffNavigation crewId={crewId || undefined} />

        <div className="w-full">
          {selectedTrace ? (
            <Card>
              <CardHeader>
                <CardTitle>{selectedTrace.crew_name}</CardTitle>
              </CardHeader>
              <CardContent>
                <Tabs
                  defaultValue="overview"
                  value={activeTab}
                  onValueChange={setActiveTab}
                  className="w-full"
                >
                  <TabsList className="grid grid-cols-4 mb-4">
                    <TabsTrigger
                      value="overview"
                      className="flex items-center gap-1"
                    >
                      <Info className="h-4 w-4" />
                      <span>Overview</span>
                    </TabsTrigger>
                    <TabsTrigger value="agents" className="flex items-center gap-1">
                      <Users className="h-4 w-4" />
                      <span>Agents</span>
                    </TabsTrigger>
                    <TabsTrigger value="tasks">Tasks</TabsTrigger>
                    <TabsTrigger value="events" className="flex items-center gap-1">
                      <Clock className="h-4 w-4" />
                      <span>Events</span>
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="overview">
                    {renderOverviewWithTimeline()}
                  </TabsContent>

                  <TabsContent value="agents">{renderAgents()}</TabsContent>

                  <TabsContent value="tasks">{renderTasks()}</TabsContent>

                  <TabsContent value="events">{renderEvents()}</TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          ) : loading ? (
            <div className="flex justify-center items-center p-8">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : (
            <div className="text-center p-8 text-gray-500">
              Select a trace to view details
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
