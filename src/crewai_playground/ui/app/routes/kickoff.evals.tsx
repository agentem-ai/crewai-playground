import React, { useState, useEffect } from "react";
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
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "../components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetClose,
} from "../components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import {
  AlertCircle,
  BarChart3,
  CheckCircle,
  ChevronRight,
  Clock,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  X,
  XCircle,
} from "lucide-react";
import { Separator } from "../components/ui/separator";

// Define types for evaluation data
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

interface AgentEvaluation {
  agent_id: string;
  agent_role: string;
  overall_score: number;
  metrics: Record<string, { score: number; feedback: string }>;
  score: number;
  feedback: string;
  task_count: number;
}

interface EvaluationResults {
  agent_results: Record<string, AgentEvaluation>;
  overall_score: number;
  total_agents: number;
  aggregation_strategy: string;
}

// Helper functions for UI elements
function getStatusIcon(status: EvaluationRun["status"]) {
  switch (status) {
    case "running":
      return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
    case "completed":
      return <CheckCircle className="h-4 w-4 text-green-500" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-red-500" />;
    case "pending":
      return <Clock className="h-4 w-4 text-yellow-500" />;
    default:
      return <AlertCircle className="h-4 w-4 text-gray-500" />;
  }
}

function getStatusBadge(status: EvaluationRun["status"]) {
  switch (status) {
    case "running":
      return (
        <Badge
          variant="outline"
          className="bg-blue-50 text-blue-700 border-blue-200"
        >
          Running
        </Badge>
      );
    case "completed":
      return (
        <Badge
          variant="outline"
          className="bg-green-50 text-green-700 border-green-200"
        >
          Completed
        </Badge>
      );
    case "failed":
      return (
        <Badge
          variant="outline"
          className="bg-red-50 text-red-700 border-red-200"
        >
          Failed
        </Badge>
      );
    case "pending":
      return (
        <Badge
          variant="outline"
          className="bg-yellow-50 text-yellow-700 border-yellow-200"
        >
          Pending
        </Badge>
      );
  }
}

function getScoreColor(score: number | null | undefined) {
  if (score == null) return "text-gray-500";
  if (score >= 8) return "text-green-600";
  if (score >= 6) return "text-cyan-600";
  if (score >= 4) return "text-yellow-600";
  return "text-red-600";
}

function formatDuration(start: string, end?: string) {
  if (!end) return "In progress";
  const startDate = new Date(start);
  const endDate = new Date(end);
  const durationMs = endDate.getTime() - startDate.getTime();
  const seconds = Math.floor(durationMs / 1000);

  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

export function meta() {
  return [
    { title: "CrewAI - Evaluation Results" },
    {
      name: "description",
      content: "View evaluation results for your CrewAI agents",
    },
  ];
}

export default function KickoffEvalsPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const crewId = searchParams.get("crewId");

  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [selectedEvaluation, setSelectedEvaluation] = useState<string | null>(
    null
  );
  const [evaluationResults, setEvaluationResults] =
    useState<EvaluationResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedEvaluationDetails, setSelectedEvaluationDetails] =
    useState<EvaluationRun | null>(null);

  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newEvaluation, setNewEvaluation] = useState({
    iterations: 1,
    aggregation_strategy: "simple_average",
    test_inputs: {},
  });
  const [testInputsJson, setTestInputsJson] = useState(
    JSON.stringify(
      { query: "Evaluate agent performance on this task" },
      null,
      2
    )
  );
  const [aggregationStrategies] = useState([
    {
      id: "simple_average",
      name: "Simple Average",
      description: "Equal weight to all tasks",
    },
    {
      id: "weighted_by_complexity",
      name: "Weighted by Complexity",
      description: "Weight by task complexity",
    },
    {
      id: "best_performance",
      name: "Best Performance",
      description: "Use best scores across tasks",
    },
    {
      id: "worst_performance",
      name: "Worst Performance",
      description: "Use worst scores across tasks",
    },
  ]);

  // Create a new evaluation
  const createEvaluation = async () => {
    let parsedTestInputs = {};
    try {
      parsedTestInputs = JSON.parse(testInputsJson);
    } catch (error) {
      alert("Invalid JSON in test inputs. Please check the format.");
      return;
    }

    setIsCreating(true);
    try {
      const evaluationData = {
        name: `Evaluation for ${crewId}`,
        crew_ids: [crewId],
        iterations: newEvaluation.iterations,
        aggregation_strategy: newEvaluation.aggregation_strategy,
        test_inputs: parsedTestInputs,
      };

      const response = await fetch("/api/evaluations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(evaluationData),
      });

      const data = await response.json();
      if (data.status === "success") {
        setShowCreateModal(false);
        setNewEvaluation({
          iterations: 1,
          aggregation_strategy: "simple_average",
          test_inputs: {},
        });
        setTestInputsJson(
          JSON.stringify(
            { query: "Evaluate agent performance on this task" },
            null,
            2
          )
        );
        setRefreshKey((prev) => prev + 1);
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

  // Fetch evaluations for the crew
  useEffect(() => {
    if (!crewId) return;

    async function fetchEvaluations() {
      setLoading(true);
      try {
        const response = await fetch(`/api/evaluations?crew_id=${crewId}`);
        if (response.ok) {
          const data = await response.json();
          // API returns evaluations in data.runs, not data.evaluations
          setEvaluations(data.data?.runs || []);
        }
      } catch (error) {
        console.error("Error fetching evaluations:", error);
      } finally {
        setLoading(false);
      }
    }

    fetchEvaluations();
  }, [crewId, refreshKey]);

  // Auto-refresh running evaluations
  useEffect(() => {
    const interval = setInterval(() => {
      const hasRunningEvaluations = evaluations.some(
        (evaluation) => evaluation.status === "running"
      );
      if (hasRunningEvaluations) {
        // Refresh evaluations when there are running ones
        fetch(`/api/evaluations?crew_id=${crewId}`)
          .then(response => response.json())
          .then(data => {
            if (data.data?.runs) {
              setEvaluations(data.data.runs);
            }
          })
          .catch(error => console.error("Error refreshing evaluations:", error));
      }
    }, 5000); // Refresh every 5 seconds

    return () => clearInterval(interval);
  }, [evaluations, crewId]);

  // Fetch results for selected evaluation
  async function fetchEvaluationResults(evalId: string) {
    setResultsLoading(true);
    try {
      const response = await fetch(`/api/evaluations/${evalId}/results`);
      
      if (response.ok) {
        const apiResponse = await response.json();
        
        // Extract the actual evaluation results from the nested structure
        const rawData = apiResponse.status === 'success' ? apiResponse.data : null;
        
        if (rawData) {
          // Transform the data structure to match UI expectations
          const transformedData = {
            overall_score: rawData.summary?.overall_score || rawData.results?.summary?.overall_score,
            total_agents: rawData.summary?.agent_count || rawData.results?.summary?.total_agents,
            aggregation_strategy: rawData.results?.summary?.aggregation_strategy,
            agent_results: rawData.results?.agent_results || {}
          };
          setEvaluationResults(transformedData);
        } else {
          setEvaluationResults(null);
        }
      } else {
        setEvaluationResults(null);
      }
    } catch (error) {
      console.error("Error fetching evaluation results:", error);
      setEvaluationResults(null);
    } finally {
      setResultsLoading(false);
    }
  }

  // Handle evaluation selection
  const handleEvaluationSelect = async (evalId: string) => {
    setSelectedEvaluation(evalId);
    const evalDetails = evaluations.find((e) => e.id === evalId);
    if (evalDetails) {
      setSelectedEvaluationDetails(evalDetails);
      setDrawerOpen(true);
      await fetchEvaluationResults(evalId);
    }
  };

  // Refresh evaluations
  const handleRefresh = () => {
    setRefreshKey((prev) => prev + 1);
  };

  return (
    <Layout>
      <div className="w-full">
        {/* Navigation */}
        <KickoffNavigation />

        {/* Evaluation Results Drawer */}
        <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
          <SheetContent className="w-[75%] sm:max-w-[75%] overflow-y-auto">
            <SheetHeader className="mb-6">
              <SheetTitle className="text-2xl">Evaluation Results</SheetTitle>
              <SheetDescription>
                Detailed performance metrics and agent evaluations
              </SheetDescription>
            </SheetHeader>


            {resultsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-indigo-500 mr-2" />
                <p>Loading evaluation results...</p>
              </div>
            ) : !evaluationResults ? (
              <div className="text-center py-12">
                <AlertCircle className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                <h3 className="text-lg font-medium mb-2">
                  No Results Available
                </h3>
                <p className="text-gray-500">
                  {selectedEvaluationDetails?.status === "running"
                    ? "Evaluation is still running. Results will be available when complete."
                    : "No evaluation results are available for this evaluation."}
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Evaluation Summary */}
                <div>
                  <h3 className="text-lg font-semibold mb-4">
                    Evaluation Summary
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-center">
                      <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
                        Overall Score
                      </div>
                      <div
                        className={`text-2xl font-bold ${getScoreColor(
                          evaluationResults.overall_score
                        )}`}
                      >
                        {evaluationResults.overall_score != null
                          ? evaluationResults?.overall_score?.toFixed(1)
                          : "N/A"}
                      </div>
                    </div>
                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-center">
                      <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
                        Agents Evaluated
                      </div>
                      <div className="text-2xl font-bold">
                        {evaluationResults.total_agents}
                      </div>
                    </div>
                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-center">
                      <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
                        Aggregation Strategy
                      </div>
                      <div className="text-sm font-medium capitalize">
                        {evaluationResults?.aggregation_strategy?.replace(
                          "_",
                          " "
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Agent Performance Details */}
                <div>
                  <h3 className="text-lg font-semibold mb-4">
                    Agent Performance
                  </h3>
                  <div className="space-y-4">
                    {evaluationResults?.agent_results ? (
                      Object.entries(evaluationResults.agent_results).map(
                        ([agentId, agentResult]) => (
                          <div key={agentId} className="border rounded-lg p-4">
                            <div className="flex justify-between items-center mb-3">
                              <div>
                                <h4 className="font-semibold">
                                  {agentResult.agent_role}
                                </h4>
                                <p className="text-sm text-gray-500">
                                  ID: {agentId}
                                </p>
                              </div>
                              <div className="text-right">
                                <div
                                  className={`text-xl font-bold ${getScoreColor(
                                    agentResult.overall_score
                                  )}`}
                                >
                                  {agentResult.overall_score != null
                                    ? agentResult?.overall_score?.toFixed(1)
                                    : "N/A"}
                                </div>
                                <div className="text-sm text-gray-500">
                                  Overall Score
                                </div>
                              </div>
                            </div>

                            {agentResult.feedback && (
                              <div className="mb-3">
                                <p className="text-sm text-gray-600 dark:text-gray-300">
                                  {agentResult.feedback}
                                </p>
                              </div>
                            )}

                            {agentResult.metrics &&
                              Object.keys(agentResult.metrics).length > 0 && (
                                <div>
                                  <h5 className="font-medium mb-2 text-sm">
                                    Metric Breakdown:
                                  </h5>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                    {Object.entries(agentResult.metrics).map(
                                      ([metricName, metric]) => (
                                        <div
                                          key={metricName}
                                          className="bg-gray-50 dark:bg-gray-800 rounded p-2"
                                        >
                                          <div className="flex justify-between items-center mb-1">
                                            <span className="text-sm font-medium capitalize">
                                              {metricName?.replace("_", " ")}
                                            </span>
                                            <span
                                              className={`text-sm font-bold ${getScoreColor(
                                                metric.score
                                              )}`}
                                            >
                                              {metric.score != null
                                                ? metric?.score?.toFixed(1)
                                                : "N/A"}
                                            </span>
                                          </div>
                                          {metric.feedback && (
                                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                              {metric.feedback}
                                            </p>
                                          )}
                                        </div>
                                      )
                                    )}
                                  </div>
                                </div>
                              )}
                          </div>
                        )
                      )
                    ) : (
                      <div className="text-center py-4 text-gray-500">
                        No agent performance data available
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            <SheetClose onClick={() => setDrawerOpen(false)} />
          </SheetContent>
        </Sheet>

        {/* Create Evaluation Modal */}
        <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create New Evaluation</DialogTitle>
              <DialogDescription>
                Configure and start a new evaluation for your crew
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="iterations">Number of Iterations</Label>
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
                <p className="text-xs text-muted-foreground">
                  Higher iterations provide more reliable results but take
                  longer to complete
                </p>
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
                        <div className="flex flex-col">
                          <span>{strategy.name}</span>
                          <span className="text-xs text-muted-foreground">
                            {strategy.description}
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="test-inputs">Test Inputs (JSON)</Label>
                <p className="text-sm text-muted-foreground">
                  Define the inputs that will be passed to the crew during
                  evaluation.
                </p>
                <Textarea
                  id="test-inputs"
                  placeholder="Enter test inputs as JSON..."
                  value={testInputsJson}
                  onChange={(e) => setTestInputsJson(e.target.value)}
                  rows={8}
                  className="font-mono text-sm"
                />
                <div className="text-xs text-muted-foreground">
                  <strong>Example:</strong>{" "}
                  {`{"query": "Analyze market trends", "topic": "AI technology"}`}
                </div>
              </div>

              <div className="flex justify-end space-x-2 pt-4">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowCreateModal(false);
                    setNewEvaluation({
                      iterations: 1,
                      aggregation_strategy: "simple_average",
                      test_inputs: {},
                    });
                    setTestInputsJson(
                      JSON.stringify(
                        { query: "Evaluate agent performance on this task" },
                        null,
                        2
                      )
                    );
                  }}
                >
                  <X className="h-4 w-4 mr-2" />
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
            </div>
          </DialogContent>
        </Dialog>

        {loading ? (
          <Card className="mb-6">
            <CardContent className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mr-2" />
              <p>Loading evaluations...</p>
            </CardContent>
          </Card>
        ) : evaluations.length === 0 ? (
          <Card className="mb-6">
            <CardContent className="py-12">
              <div className="text-center">
                <BarChart3 className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                <h3 className="text-lg font-medium mb-2">
                  No Evaluations Found
                </h3>
                <p className="text-gray-500 mb-4">
                  There are no evaluations for this crew yet.
                </p>
                <Button onClick={() => setShowCreateModal(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  New Evaluation
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-6">
            {/* Evaluations List */}
            <Card>
              <CardHeader className="flex flex-row justify-between items-start">
                <div>
                  <CardTitle>Evaluations</CardTitle>
                  <CardDescription>
                    Click an evaluation to view detailed results
                  </CardDescription>
                </div>
                <Button size="sm" onClick={() => setShowCreateModal(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  New Evaluation
                </Button>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {evaluations.map((evaluation) => (
                    <div
                      key={evaluation.id}
                      className="border rounded-lg overflow-hidden hover:bg-muted/10 transition-all cursor-pointer w-full"
                      onClick={() => handleEvaluationSelect(evaluation.id)}
                    >
                      <div className="p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          {/* Left section - Status and details */}
                          <div className="flex items-center space-x-4">
                            {getStatusIcon(evaluation.status)}
                            <div>
                              <div className="flex items-center">
                                <span className="font-medium mr-2">
                                  {evaluation.iterations}{" "}
                                  {evaluation.iterations === 1
                                    ? "Iteration"
                                    : "Iterations"}
                                </span>
                                {getStatusBadge(evaluation.status)}
                              </div>
                              <div className="text-sm text-muted-foreground mt-1">
                                {evaluation.agentCount} agents •{" "}
                                {formatDuration(
                                  evaluation.startTime,
                                  evaluation.endTime
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Right section - Progress and score */}
                          <div className="flex items-center space-x-6">
                            {evaluation.status === "running" && (
                              <div className="flex items-center space-x-3 w-48">
                                <span className="text-sm text-muted-foreground whitespace-nowrap">
                                  Progress: {evaluation?.progress?.toFixed(0)}%
                                </span>
                                <Progress
                                  value={evaluation.progress}
                                  className="h-2 w-24"
                                />
                              </div>
                            )}

                            {evaluation.overallScore !== undefined && (
                              <div className="flex items-center space-x-2">
                                <span className="text-sm text-muted-foreground whitespace-nowrap">
                                  Score:
                                </span>
                                <span
                                  className={`font-bold ${getScoreColor(
                                    evaluation.overallScore
                                  )}`}
                                >
                                  {evaluation?.overallScore?.toFixed(1)}
                                </span>
                              </div>
                            )}

                            <Button variant="ghost" size="sm" className="ml-2">
                              <ChevronRight className="h-5 w-5" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </Layout>
  );
}
