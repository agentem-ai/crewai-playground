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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
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
  ArrowLeft,
  BarChart3,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  TrendingUp,
  Plus,
  Play,
  X,
} from "lucide-react";
import { ScrollArea } from "../components/ui/scroll-area";
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
  score: number;
  feedback: string;
  task_count: number;
}

interface EvaluationResults {
  agent_results: Record<string, AgentEvaluation>;
  summary: {
    overall_score: number;
    total_agents: number;
    aggregation_strategy: string;
  };
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

function getScoreColor(score: number) {
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
  const [activeTab, setActiveTab] = useState("overview");
  const [refreshKey, setRefreshKey] = useState(0);
  
  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newEvaluation, setNewEvaluation] = useState({
    iterations: 1,
    aggregation_strategy: "simple_average",
    test_inputs: {}
  });
  const [testInputsJson, setTestInputsJson] = useState(
    JSON.stringify(
      {
        query: "Evaluate agent performance on this task"
      },
      null,
      2
    )
  );
  const [aggregationStrategies, setAggregationStrategies] = useState([
    {
      id: "simple_average",
      name: "Simple Average",
      description: "Equal weight to all tasks"
    },
    {
      id: "weighted_by_complexity",
      name: "Weighted by Complexity",
      description: "Weight by task complexity"
    },
    {
      id: "best_performance",
      name: "Best Performance",
      description: "Use best scores across tasks"
    },
    {
      id: "worst_performance",
      name: "Worst Performance",
      description: "Use worst scores across tasks"
    }
  ]);

  // Create a new evaluation
  const createEvaluation = async () => {
    // Parse and validate test inputs JSON
    let parsedTestInputs = {};
    try {
      parsedTestInputs = JSON.parse(testInputsJson);
    } catch (error) {
      alert("Invalid JSON in test inputs. Please check the format.");
      return;
    }

    setIsCreating(true);
    try {
      // Create evaluation with the current crew ID
      const evaluationData = {
        name: `Evaluation for ${crewId}`, // Auto-generate a name based on crew ID
        crew_ids: [crewId], // Use the current crew ID
        iterations: newEvaluation.iterations,
        aggregation_strategy: newEvaluation.aggregation_strategy,
        test_inputs: parsedTestInputs,
        // No metric_categories means all metrics will be used
      };

      const response = await fetch("/api/evaluations", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(evaluationData),
      });

      const data = await response.json();
      if (data.status === "success") {
        setShowCreateModal(false);
        // Reset form
        setNewEvaluation({
          iterations: 1,
          aggregation_strategy: "simple_average",
          test_inputs: {}
        });
        setTestInputsJson(
          JSON.stringify(
            { query: "Evaluate agent performance on this task" },
            null,
            2
          )
        );
        // Refresh evaluations list
        setRefreshKey(prev => prev + 1);
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
          setEvaluations(data.evaluations || []);

          // Select the first evaluation by default if available
          if (
            data.evaluations &&
            data.evaluations.length > 0 &&
            !selectedEvaluation
          ) {
            setSelectedEvaluation(data.evaluations[0].id);
            fetchEvaluationResults(data.evaluations[0].id);
          }
        }
      } catch (error) {
        console.error("Error fetching evaluations:", error);
      } finally {
        setLoading(false);
      }
    }

    fetchEvaluations();

    // Set up polling for updates if there are running evaluations
    const interval = setInterval(() => {
      if (evaluations.some((e) => e.status === "running")) {
        fetchEvaluations();
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [crewId, refreshKey]);

  // Fetch results for selected evaluation
  async function fetchEvaluationResults(evalId: string) {
    setResultsLoading(true);
    try {
      const response = await fetch(`/api/evaluations/${evalId}/results`);
      if (response.ok) {
        const data = await response.json();
        setEvaluationResults(data);
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
  const handleEvaluationSelect = (evalId: string) => {
    setSelectedEvaluation(evalId);
    fetchEvaluationResults(evalId);
  };

  // Refresh evaluations
  const handleRefresh = () => {
    setRefreshKey((prev) => prev + 1);
  };

  // Get selected evaluation
  const selectedEval = evaluations.find((e) => e.id === selectedEvaluation);

  return (
    <Layout>
      <div className="w-full">
        {/* Create Evaluation Modal */}
        <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create New Evaluation</DialogTitle>
              <DialogDescription>
                Configure and start a new agent evaluation for this crew
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6">
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
                  Higher iterations provide more reliable results but take longer to complete
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
                          <span className="text-xs text-muted-foreground">{strategy.description}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Test Inputs Section */}
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
                    // Reset form
                    setNewEvaluation({
                      iterations: 1,
                      aggregation_strategy: "simple_average",
                      test_inputs: {},
                    });
                    setTestInputsJson(
                      JSON.stringify(
                        {
                          query: "Evaluate agent performance on this task",
                        },
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Evaluations List */}
            <Card className="md:col-span-1">
              <CardHeader className="flex justify-between items-start">
                <div>
                  <CardTitle>Evaluations</CardTitle>
                  <CardDescription>
                    Select an evaluation to view details
                  </CardDescription>
                </div>
                <Button size="sm" onClick={() => setShowCreateModal(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  New Evaluation
                </Button>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[500px] pr-4">
                  {evaluations.map((evaluation) => (
                    <div
                      key={evaluation.id}
                      className={`mb-3 p-3 rounded-md cursor-pointer border transition-colors ${
                        selectedEvaluation === evaluation.id
                          ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30"
                          : "border-gray-200 hover:border-gray-300 dark:border-gray-700 dark:hover:border-gray-600"
                      }`}
                      onClick={() => handleEvaluationSelect(evaluation.id)}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="font-medium truncate mr-2">
                          {evaluation.name ||
                            `Evaluation ${evaluation.id.substring(0, 8)}`}
                        </div>
                        {getStatusBadge(evaluation.status)}
                      </div>

                      {evaluation.status === "running" && (
                        <Progress
                          value={evaluation.progress}
                          className="h-1 mb-2"
                        />
                      )}

                      <div className="flex items-center text-xs text-gray-500 dark:text-gray-400">
                        <Clock className="h-3 w-3 mr-1" />
                        {new Date(evaluation.startTime).toLocaleString()}
                      </div>

                      <div className="flex items-center justify-between mt-2 text-xs">
                        <span className="text-gray-500 dark:text-gray-400">
                          {evaluation.agentCount} agents •{" "}
                          {evaluation.iterations} iterations
                        </span>

                        {evaluation.overallScore !== undefined && (
                          <span
                            className={`font-semibold ${getScoreColor(
                              evaluation.overallScore
                            )}`}
                          >
                            Score: {evaluation.overallScore.toFixed(1)}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </ScrollArea>
              </CardContent>
            </Card>

            {/* Evaluation Details */}
            <Card className="md:col-span-2">
              {selectedEval ? (
                <>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle>
                          {selectedEval.name ||
                            `Evaluation ${selectedEval.id.substring(0, 8)}`}
                        </CardTitle>
                        <CardDescription>
                          {new Date(selectedEval.startTime).toLocaleString()}
                          {selectedEval.endTime &&
                            ` • Duration: ${formatDuration(
                              selectedEval.startTime,
                              selectedEval.endTime
                            )}`}
                        </CardDescription>
                      </div>
                      <div className="flex items-center">
                        {getStatusIcon(selectedEval.status)}
                        <span className="ml-2 text-sm">
                          {selectedEval.status.charAt(0).toUpperCase() +
                            selectedEval.status.slice(1)}
                        </span>
                      </div>
                    </div>
                  </CardHeader>

                  <CardContent>
                    {selectedEval.status === "running" && (
                      <div className="mb-4">
                        <div className="flex justify-between mb-1 text-sm">
                          <span>Progress</span>
                          <span>{Math.round(selectedEval.progress)}%</span>
                        </div>
                        <Progress
                          value={selectedEval.progress}
                          className="h-2"
                        />
                      </div>
                    )}

                    <Tabs
                      value={activeTab}
                      onValueChange={setActiveTab}
                      className="mt-2"
                    >
                      <TabsList className="mb-4">
                        <TabsTrigger value="overview">Overview</TabsTrigger>
                        <TabsTrigger value="agents">Agent Results</TabsTrigger>
                        <TabsTrigger value="metrics">Metrics</TabsTrigger>
                      </TabsList>

                      <TabsContent value="overview">
                        {resultsLoading ? (
                          <div className="flex items-center justify-center py-12">
                            <Loader2 className="h-6 w-6 animate-spin text-indigo-500 mr-2" />
                            <p>Loading results...</p>
                          </div>
                        ) : !evaluationResults ? (
                          <div className="text-center py-12">
                            <AlertCircle className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                            <h3 className="text-lg font-medium mb-2">
                              No Results Available
                            </h3>
                            <p className="text-gray-500">
                              {selectedEval.status === "running"
                                ? "Evaluation is still running. Results will be available when complete."
                                : "No evaluation results are available for this evaluation."}
                            </p>
                          </div>
                        ) : (
                          <div>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                              <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-center">
                                <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
                                  Overall Score
                                </div>
                                <div
                                  className={`text-2xl font-bold ${getScoreColor(
                                    evaluationResults.overall_score
                                  )}`}
                                >
                                  {evaluationResults.overall_score.toFixed(1)}
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
                                  Iterations
                                </div>
                                <div className="text-2xl font-bold">
                                  {selectedEval.iterations}
                                </div>
                              </div>
                            </div>

                            <h3 className="font-semibold mb-2 flex items-center">
                              <TrendingUp className="h-4 w-4 mr-1" />
                              Performance Summary
                            </h3>
                            <p className="text-gray-600 dark:text-gray-300 mb-4">
                              This evaluation used the{" "}
                              <span className="font-medium">
                                {evaluationResults.aggregation_strategy}
                              </span>{" "}
                              aggregation strategy across{" "}
                              {selectedEval.iterations} iterations to evaluate{" "}
                              {evaluationResults.total_agents} agents.
                            </p>
                          </div>
                        )}
                      </TabsContent>

                      <TabsContent value="agents">
                        {resultsLoading ? (
                          <div className="flex items-center justify-center py-12">
                            <Loader2 className="h-6 w-6 animate-spin text-indigo-500 mr-2" />
                            <p>Loading agent results...</p>
                          </div>
                        ) : !evaluationResults?.agent_results ? (
                          <div className="text-center py-12">
                            <AlertCircle className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                            <h3 className="text-lg font-medium mb-2">
                              No Agent Results
                            </h3>
                            <p className="text-gray-500">
                              No agent evaluation results are available.
                            </p>
                          </div>
                        ) : (
                          <div>
                            {Object.entries(
                              evaluationResults.agent_results
                            ).map(([agentId, agentResult]) => (
                              <div
                                key={agentId}
                                className="mb-6 border rounded-lg p-4"
                              >
                                <div className="flex justify-between items-center mb-3">
                                  <h3 className="font-semibold">
                                    {agentResult.agent_role}
                                  </h3>
                                  <div
                                    className={`text-lg font-bold ${getScoreColor(
                                      agentResult.overall_score
                                    )}`}
                                  >
                                    {agentResult.overall_score.toFixed(1)}
                                  </div>
                                </div>

                                <Separator className="my-3" />

                                <div className="space-y-3">
                                  {Object.entries(
                                    agentResult.metrics || {}
                                  ).map(([metricName, metric]) => (
                                    <div
                                      key={metricName}
                                      className="grid grid-cols-12 gap-2"
                                    >
                                      <div className="col-span-4 text-sm font-medium">
                                        {metricName.replace(/_/g, " ")}
                                      </div>
                                      <div className="col-span-2">
                                        <span
                                          className={`text-sm font-semibold ${getScoreColor(
                                            metric.score
                                          )}`}
                                        >
                                          {metric.score.toFixed(1)}
                                        </span>
                                      </div>
                                      <div className="col-span-6 text-sm text-gray-600 dark:text-gray-300">
                                        {metric.feedback}
                                      </div>
                                    </div>
                                  ))}
                                </div>

                                <Separator className="my-3" />

                                <div className="text-sm text-gray-600 dark:text-gray-300">
                                  <p className="font-medium mb-1">
                                    Overall Feedback:
                                  </p>
                                  <p>{agentResult.feedback}</p>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      <TabsContent value="metrics">
                        {resultsLoading ? (
                          <div className="flex items-center justify-center py-12">
                            <Loader2 className="h-6 w-6 animate-spin text-indigo-500 mr-2" />
                            <p>Loading metrics...</p>
                          </div>
                        ) : !evaluationResults?.agent_results ? (
                          <div className="text-center py-12">
                            <AlertCircle className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                            <h3 className="text-lg font-medium mb-2">
                              No Metrics Available
                            </h3>
                            <p className="text-gray-500">
                              No evaluation metrics are available.
                            </p>
                          </div>
                        ) : (
                          <div>
                            {/* Extract unique metrics across all agents */}
                            {(() => {
                              const metrics: Record<
                                string,
                                { scores: number[]; feedbacks: string[] }
                              > = {};

                              Object.values(
                                evaluationResults.agent_results
                              ).forEach((agent) => {
                                Object.entries(agent.metrics || {}).forEach(
                                  ([name, data]) => {
                                    if (!metrics[name]) {
                                      metrics[name] = {
                                        scores: [],
                                        feedbacks: [],
                                      };
                                    }
                                    metrics[name].scores.push(data.score);
                                    metrics[name].feedbacks.push(data.feedback);
                                  }
                                );
                              });

                              return Object.entries(metrics).map(
                                ([metricName, data]) => {
                                  const avgScore =
                                    data.scores.reduce((a, b) => a + b, 0) /
                                    data.scores.length;

                                  return (
                                    <div
                                      key={metricName}
                                      className="mb-6 border rounded-lg p-4"
                                    >
                                      <div className="flex justify-between items-center mb-3">
                                        <h3 className="font-semibold">
                                          {metricName.replace(/_/g, " ")}
                                        </h3>
                                        <div
                                          className={`text-lg font-bold ${getScoreColor(
                                            avgScore
                                          )}`}
                                        >
                                          {avgScore.toFixed(1)}
                                        </div>
                                      </div>

                                      <div className="text-sm text-gray-600 dark:text-gray-300 mb-3">
                                        Average score across{" "}
                                        {data.scores.length} agents
                                      </div>

                                      <Separator className="my-3" />

                                      <div className="space-y-3">
                                        {data.feedbacks.map(
                                          (feedback, index) => (
                                            <div
                                              key={index}
                                              className="text-sm"
                                            >
                                              <span
                                                className={`font-semibold ${getScoreColor(
                                                  data.scores[index]
                                                )}`}
                                              >
                                                {data.scores[index].toFixed(1)}:
                                              </span>{" "}
                                              {feedback}
                                            </div>
                                          )
                                        )}
                                      </div>
                                    </div>
                                  );
                                }
                              );
                            })()}
                          </div>
                        )}
                      </TabsContent>
                    </Tabs>
                  </CardContent>
                </>
              ) : (
                <CardContent className="flex items-center justify-center py-12 text-center">
                  <div>
                    <BarChart3 className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                    <h3 className="text-lg font-medium mb-2">
                      No Evaluation Selected
                    </h3>
                    <p className="text-gray-500">
                      Select an evaluation from the list to view details
                    </p>
                  </div>
                </CardContent>
              )}
            </Card>
          </div>
        )}
      </div>
    </Layout>
  );
}
