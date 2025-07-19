import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui/tabs";
import {
  Play,
  BarChart3,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Plus,
  Filter,
  Download,
  Eye,
  Settings,
  Trash2,
  RefreshCw,
  TrendingUp,
  Users,
  Target,
  Zap,
} from "lucide-react";
import { cn } from "../lib/utils";
import { Layout } from "../components/Layout";

interface EvaluationRun {
  id: string;
  name: string;
  status: "running" | "completed" | "failed" | "pending";
  progress: number;
  startTime: string;
  endTime?: string;
  agentCount: number;
  metricCount: number;
  overallScore?: number;
  iterations: number;
}

interface MetricScore {
  category: string;
  score: number;
  feedback: string;
}

interface AgentEvaluation {
  agent_id: string;
  agent_role: string;
  overall_score: number;
  metrics: Record<string, { score: number; feedback: string }>;
  task_count: number;
}

interface EvaluationResults {
  agent_results: Record<string, AgentEvaluation>;
  summary: {
    overall_score: number;
    total_agents: number;
    aggregation_strategy: string;
  };
}

interface Crew {
  id: string;
  name: string;
  description?: string;
}

interface Metric {
  id: string;
  name: string;
  description: string;
}

interface AggregationStrategy {
  id: string;
  name: string;
  description: string;
}

interface EvaluationConfig {
  name: string;
  crew_ids: string[];
  metric_categories?: string[];
  iterations?: number;
  aggregation_strategy?: string;
  test_inputs?: Record<string, any>;
}

const getStatusIcon = (status: EvaluationRun["status"]) => {
  switch (status) {
    case "completed":
      return <CheckCircle className="h-4 w-4 text-green-500" />;
    case "running":
      return <Clock className="h-4 w-4 text-blue-500 animate-spin" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-red-500" />;
    case "pending":
      return <AlertCircle className="h-4 w-4 text-yellow-500" />;
  }
};

const getStatusBadge = (status: EvaluationRun["status"]) => {
  const variants = {
    completed: "bg-green-100 text-green-800 border-green-200",
    running: "bg-blue-100 text-blue-800 border-blue-200",
    failed: "bg-red-100 text-red-800 border-red-200",
    pending: "bg-yellow-100 text-yellow-800 border-yellow-200",
  };

  return (
    <Badge variant="outline" className={variants[status]}>
      {getStatusIcon(status)}
      <span className="ml-1 capitalize">{status}</span>
    </Badge>
  );
};

const getScoreColor = (score: number) => {
  if (score >= 8) return "text-green-600";
  if (score >= 6) return "text-blue-600";
  if (score >= 4) return "text-yellow-600";
  return "text-red-600";
};

const formatDuration = (start: string, end?: string) => {
  const startTime = new Date(start);
  const endTime = end ? new Date(end) : new Date();
  const duration = Math.floor((endTime.getTime() - startTime.getTime()) / 1000);

  if (duration < 60) return `${duration}s`;
  if (duration < 3600) return `${Math.floor(duration / 60)}m ${duration % 60}s`;
  return `${Math.floor(duration / 3600)}h ${Math.floor(
    (duration % 3600) / 60
  )}m`;
};

export default function EvaluationsPage() {
  const [selectedTab, setSelectedTab] = useState("overview");
  const [evaluationRuns, setEvaluationRuns] = useState<EvaluationRun[]>([]);
  const [crews, setCrews] = useState<Crew[]>([]);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [aggregationStrategies, setAggregationStrategies] = useState<
    AggregationStrategy[]
  >([]);
  const [selectedEvaluation, setSelectedEvaluation] = useState<string | null>(
    null
  );
  const [evaluationResults, setEvaluationResults] =
    useState<EvaluationResults | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Form state for creating new evaluations
  const [newEvaluation, setNewEvaluation] = useState<EvaluationConfig>({
    name: "",
    crew_ids: [],
    metric_categories: [],
    iterations: 1,
    aggregation_strategy: "simple_average",
  });

  // Fetch data on component mount
  useEffect(() => {
    fetchEvaluations();
    fetchCrews();
    fetchMetrics();
  }, []);

  // Auto-refresh running evaluations
  useEffect(() => {
    const interval = setInterval(() => {
      const hasRunningEvaluations = evaluationRuns.some(
        (run) => run.status === "running"
      );
      if (hasRunningEvaluations) {
        fetchEvaluations();
      }
    }, 5000); // Refresh every 5 seconds

    return () => clearInterval(interval);
  }, [evaluationRuns]);

  const fetchEvaluations = async () => {
    try {
      const response = await fetch("/api/evaluations");
      const data = await response.json();
      if (data.status === "success") {
        setEvaluationRuns(data.data.runs);
      }
    } catch (error) {
      console.error("Error fetching evaluations:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchCrews = async () => {
    try {
      const response = await fetch("/api/crews");
      const data = await response.json();
      if (data.status === "success") {
        setCrews(
          data.crews.map((crew: any) => ({
            id: crew.id,
            name: crew.name,
            description: crew.description,
          }))
        );
      }
    } catch (error) {
      console.error("Error fetching crews:", error);
    }
  };

  const fetchMetrics = async () => {
    try {
      const response = await fetch("/api/evaluations/metrics");
      const data = await response.json();
      if (data.status === "success") {
        setMetrics(data.data.metrics);
        setAggregationStrategies(data.data.aggregation_strategies);
      }
    } catch (error) {
      console.error("Error fetching metrics:", error);
    }
  };

  const fetchEvaluationResults = async (evaluationId: string) => {
    try {
      const response = await fetch(`/api/evaluations/${evaluationId}/results`);
      const data = await response.json();
      if (data.status === "success") {
        setEvaluationResults(data.data.results);
      }
    } catch (error) {
      console.error("Error fetching evaluation results:", error);
    }
  };

  const createEvaluation = async () => {
    if (!newEvaluation.name || newEvaluation.crew_ids.length === 0) {
      alert("Please provide a name and select at least one crew");
      return;
    }

    setIsCreating(true);
    try {
      const response = await fetch("/api/evaluations", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(newEvaluation),
      });

      const data = await response.json();
      if (data.status === "success") {
        setShowCreateForm(false);
        setNewEvaluation({
          name: "",
          crew_ids: [],
          metric_categories: [],
          iterations: 1,
          aggregation_strategy: "simple_average",
        });
        fetchEvaluations();
      } else {
        alert("Error creating evaluation: " + data.detail);
      }
    } catch (error) {
      console.error("Error creating evaluation:", error);
      alert("Error creating evaluation");
    } finally {
      setIsCreating(false);
    }
  };

  const deleteEvaluation = async (evaluationId: string) => {
    if (!confirm("Are you sure you want to delete this evaluation?")) {
      return;
    }

    try {
      const response = await fetch(`/api/evaluations/${evaluationId}`, {
        method: "DELETE",
      });

      const data = await response.json();
      if (data.status === "success") {
        fetchEvaluations();
        if (selectedEvaluation === evaluationId) {
          setSelectedEvaluation(null);
          setEvaluationResults(null);
        }
      }
    } catch (error) {
      console.error("Error deleting evaluation:", error);
    }
  };

  const viewEvaluationResults = (evaluationId: string) => {
    setSelectedEvaluation(evaluationId);
    fetchEvaluationResults(evaluationId);
    setSelectedTab("results");
  };

  return (
    <Layout>
      <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Agent Evaluations
          </h1>
          <p className="text-muted-foreground">
            Evaluate and analyze agent performance across multiple metrics and
            iterations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">
            <Filter className="h-4 w-4 mr-2" />
            Filter
          </Button>
          <Button variant="outline" size="sm">
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchEvaluations()}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button onClick={() => setShowCreateForm(true)}>
            <Plus className="h-4 w-4 mr-2" />
            New Evaluation
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Total Evaluations
            </CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{evaluationRuns.length}</div>
            <p className="text-xs text-muted-foreground">
              {evaluationRuns.filter((r) => r.status === "completed").length}{" "}
              completed
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Average Score</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div
              className={cn(
                "text-2xl font-bold",
                (() => {
                  const completedRuns = evaluationRuns.filter(
                    (r) => r.status === "completed" && r.overallScore
                  );
                  if (completedRuns.length === 0)
                    return "text-muted-foreground";
                  const avgScore =
                    completedRuns.reduce(
                      (sum, r) => sum + (r.overallScore || 0),
                      0
                    ) / completedRuns.length;
                  return getScoreColor(avgScore);
                })()
              )}
            >
              {(() => {
                const completedRuns = evaluationRuns.filter(
                  (r) => r.status === "completed" && r.overallScore
                );
                if (completedRuns.length === 0) return "-";
                const avgScore =
                  completedRuns.reduce(
                    (sum, r) => sum + (r.overallScore || 0),
                    0
                  ) / completedRuns.length;
                return avgScore.toFixed(1);
              })()}
            </div>
            <p className="text-xs text-muted-foreground">
              {evaluationRuns.filter((r) => r.status === "completed").length}{" "}
              evaluations
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Runs</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {evaluationRuns.filter((r) => r.status === "running").length}
            </div>
            <p className="text-xs text-muted-foreground">
              {evaluationRuns.filter((r) => r.status === "pending").length}{" "}
              pending
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Agents Evaluated
            </CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {evaluationRuns.reduce((sum, r) => sum + r.agentCount, 0)}
            </div>
            <p className="text-xs text-muted-foreground">Across all runs</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Tabs
        value={selectedTab}
        onValueChange={setSelectedTab}
        className="space-y-4"
      >
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="results">Results</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
          <TabsTrigger value="configuration">Configuration</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          {/* Create Evaluation Form */}
          {showCreateForm && (
            <Card>
              <CardHeader>
                <CardTitle>Create New Evaluation</CardTitle>
                <CardDescription>
                  Configure and start a new agent evaluation run
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="eval-name">Evaluation Name</Label>
                    <Input
                      id="eval-name"
                      placeholder="Enter evaluation name"
                      value={newEvaluation.name}
                      onChange={(e) =>
                        setNewEvaluation((prev) => ({
                          ...prev,
                          name: e.target.value,
                        }))
                      }
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="iterations">Iterations</Label>
                    <Input
                      id="iterations"
                      type="number"
                      min="1"
                      max="10"
                      value={newEvaluation.iterations}
                      onChange={(e) =>
                        setNewEvaluation((prev) => ({
                          ...prev,
                          iterations: parseInt(e.target.value) || 1,
                        }))
                      }
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Select Crews to Evaluate</Label>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-32 overflow-y-auto">
                    {crews.map((crew) => (
                      <div
                        key={crew.id}
                        className="flex items-center space-x-2"
                      >
                        <input
                          type="checkbox"
                          id={`crew-${crew.id}`}
                          checked={newEvaluation.crew_ids.includes(crew.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setNewEvaluation((prev) => ({
                                ...prev,
                                crew_ids: [...prev.crew_ids, crew.id],
                              }));
                            } else {
                              setNewEvaluation((prev) => ({
                                ...prev,
                                crew_ids: prev.crew_ids.filter(
                                  (id) => id !== crew.id
                                ),
                              }));
                            }
                          }}
                          className="rounded"
                        />
                        <Label htmlFor={`crew-${crew.id}`} className="text-sm">
                          {crew.name}
                        </Label>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Aggregation Strategy</Label>
                  <Select
                    value={newEvaluation.aggregation_strategy}
                    onValueChange={(value) =>
                      setNewEvaluation((prev) => ({
                        ...prev,
                        aggregation_strategy: value,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {aggregationStrategies.map((strategy) => (
                        <SelectItem key={strategy.id} value={strategy.id}>
                          {strategy.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex justify-end space-x-2">
                  <Button
                    variant="outline"
                    onClick={() => setShowCreateForm(false)}
                  >
                    Cancel
                  </Button>
                  <Button onClick={createEvaluation} disabled={isCreating}>
                    {isCreating ? (
                      <>
                        <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4 mr-2" />
                        Start Evaluation
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Recent Evaluation Runs</CardTitle>
              <CardDescription>
                Monitor the status and progress of your agent evaluations
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="text-center py-8">
                  <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-muted-foreground" />
                  <p className="text-muted-foreground">
                    Loading evaluations...
                  </p>
                </div>
              ) : evaluationRuns.length === 0 ? (
                <div className="text-center py-12">
                  <Target className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <h3 className="text-lg font-medium mb-2">
                    No Evaluations Yet
                  </h3>
                  <p className="text-muted-foreground mb-4">
                    Create your first evaluation to start analyzing agent
                    performance
                  </p>
                  <Button onClick={() => setShowCreateForm(true)}>
                    <Plus className="h-4 w-4 mr-2" />
                    Create Evaluation
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  {evaluationRuns.map((run) => (
                    <div
                      key={run.id}
                      className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-center space-x-4">
                        <div className="flex flex-col">
                          <h3 className="font-medium">{run.name}</h3>
                          <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                            <span>{run.agentCount} agents</span>
                            <span>•</span>
                            <span>{run.metricCount} metrics</span>
                            <span>•</span>
                            <span>
                              {formatDuration(run.startTime, run.endTime)}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center space-x-4">
                        {run.status === "running" && (
                          <div className="flex items-center space-x-2">
                            <Progress value={run.progress} className="w-20" />
                            <span className="text-sm text-muted-foreground">
                              {run.progress.toFixed(0)}%
                            </span>
                          </div>
                        )}

                        {run.overallScore && (
                          <div className="text-right">
                            <div
                              className={cn(
                                "text-lg font-semibold",
                                getScoreColor(run.overallScore)
                              )}
                            >
                              {run.overallScore.toFixed(1)}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              Overall Score
                            </div>
                          </div>
                        )}

                        <div className="flex items-center space-x-2">
                          {getStatusBadge(run.status)}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => viewEvaluationResults(run.id)}
                            disabled={run.status !== "completed"}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => deleteEvaluation(run.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="results" className="space-y-4">
          {selectedEvaluation && evaluationResults ? (
            <>
              {/* Results Summary */}
              <Card>
                <CardHeader>
                  <CardTitle>Evaluation Results Summary</CardTitle>
                  <CardDescription>
                    {
                      evaluationRuns.find((r) => r.id === selectedEvaluation)
                        ?.name
                    }
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="text-center">
                      <div
                        className={cn(
                          "text-3xl font-bold mb-2",
                          evaluationResults.summary?.overall_score
                            ? getScoreColor(
                                evaluationResults.summary.overall_score
                              )
                            : "text-muted-foreground"
                        )}
                      >
                        {evaluationResults.summary?.overall_score?.toFixed(1) ||
                          "N/A"}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Overall Score
                      </p>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold mb-2">
                        {evaluationResults.summary?.total_agents || 0}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Agents Evaluated
                      </p>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold mb-2">
                        {evaluationResults.summary?.aggregation_strategy
                          ?.replace("_", " ")
                          .toUpperCase() || "N/A"}
                      </div>
                      <p className="text-sm text-muted-foreground">Strategy</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Agent Results */}
              <Card>
                <CardHeader>
                  <CardTitle>Agent Performance Details</CardTitle>
                  <CardDescription>
                    Individual agent scores and feedback across all metrics
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-6">
                    {Object.entries(evaluationResults.agent_results || {}).map(
                      ([agentRole, agentData]) => (
                        <div key={agentRole} className="border rounded-lg p-4">
                          <div className="flex items-center justify-between mb-4">
                            <div>
                              <h3 className="text-lg font-semibold">
                                {agentRole}
                              </h3>
                              <p className="text-sm text-muted-foreground">
                                Agent ID: {agentData.agent_id} •{" "}
                                {agentData.task_count} tasks
                              </p>
                            </div>
                            <div className="text-right">
                              <div
                                className={cn(
                                  "text-2xl font-bold",
                                  agentData.overall_score
                                    ? getScoreColor(agentData.overall_score)
                                    : "text-muted-foreground"
                                )}
                              >
                                {agentData.overall_score?.toFixed(1) || "N/A"}
                              </div>
                              <p className="text-xs text-muted-foreground">
                                Overall Score
                              </p>
                            </div>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {Object.entries(agentData.metrics || {}).map(
                              ([metricName, metricData]) => (
                                <div
                                  key={metricName}
                                  className="bg-muted/50 rounded-lg p-3"
                                >
                                  <div className="flex items-center justify-between mb-2">
                                    <h4 className="font-medium text-sm">
                                      {metricName
                                        .replace("_", " ")
                                        .replace(/\b\w/g, (l) =>
                                          l.toUpperCase()
                                        )}
                                    </h4>
                                    <span
                                      className={cn(
                                        "text-lg font-semibold",
                                        metricData.score
                                          ? getScoreColor(metricData.score)
                                          : "text-muted-foreground"
                                      )}
                                    >
                                      {metricData.score?.toFixed(1) || "N/A"}
                                    </span>
                                  </div>
                                  {metricData.feedback && (
                                    <p className="text-xs text-muted-foreground line-clamp-3">
                                      {metricData.feedback}
                                    </p>
                                  )}
                                </div>
                              )
                            )}
                          </div>
                        </div>
                      )
                    )}
                  </div>
                </CardContent>
              </Card>
            </>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Evaluation Results</CardTitle>
                <CardDescription>
                  Detailed results and analysis from completed evaluations
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-center py-12">
                  <BarChart3 className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <h3 className="text-lg font-medium mb-2">
                    No Results Selected
                  </h3>
                  <p className="text-muted-foreground mb-4">
                    Select a completed evaluation from the overview to view
                    detailed results
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => setSelectedTab("overview")}
                  >
                    Go to Overview
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="analytics" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Performance Analytics</CardTitle>
              <CardDescription>
                Trends and insights across multiple evaluation runs
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12">
                <BarChart3 className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-medium mb-2">
                  Analytics Dashboard
                </h3>
                <p className="text-muted-foreground mb-4">
                  Performance trends and comparative analysis will be displayed
                  here
                </p>
                <Button variant="outline">Generate Report</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="configuration" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Evaluation Configuration</CardTitle>
              <CardDescription>
                Set up new evaluations and configure evaluation parameters
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12">
                <Settings className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-medium mb-2">
                  Configuration Panel
                </h3>
                <p className="text-muted-foreground mb-4">
                  Configure evaluation settings, select metrics, and set up test
                  scenarios
                </p>
                <Button>Start Configuration</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
      </div>
    </Layout>
  );
}
