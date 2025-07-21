"""
Evaluation API for CrewAI Playground

This module provides API endpoints for managing CrewAI agent evaluations.
"""

import asyncio
import datetime
import json
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from crewai_playground.crew_loader import (
    load_crew,
    load_crew_from_module,
    discover_available_crews,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check if evaluation module is available
try:
    from crewai.experimental.evaluation import (
        AgentEvaluator,
        create_default_evaluator,
        BaseEvaluator,
        MetricCategory,
        EvaluationScore,
        AgentEvaluationResult,
        EvaluationTraceCallback,
        create_evaluation_callbacks,
    )
    from crewai.utilities.events import crewai_event_bus

    EVALUATION_AVAILABLE = True

    # Register the official evaluation trace callback once at startup
    create_evaluation_callbacks().setup_listeners(crewai_event_bus)

    # Simple aggregation strategy enum since it's not available in the module
    class AggregationStrategy:
        SIMPLE_AVERAGE = "simple_average"
        WEIGHTED_BY_COMPLEXITY = "weighted_by_complexity"
        BEST_PERFORMANCE = "best_performance"
        WORST_PERFORMANCE = "worst_performance"

except ImportError:
    logging.warning(
        "CrewAI evaluation module not available. Evaluation features will be disabled."
    )
    EVALUATION_AVAILABLE = False

# Create router
router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])

# In-memory storage for evaluations and results
evaluation_runs: Dict[str, Dict[str, Any]] = {}
evaluation_results: Dict[str, Dict[str, Any]] = {}
active_evaluations: Dict[str, Any] = {}


class EvaluationConfigRequest(BaseModel):
    """Request model for evaluation configuration"""

    name: str
    crew_ids: List[str]
    metric_categories: Optional[List[str]] = None
    iterations: Optional[int] = 1
    aggregation_strategy: Optional[str] = "simple_average"
    test_inputs: Optional[Dict[str, Any]] = None


class EvaluationRunResponse(BaseModel):
    """Response model for evaluation run information"""

    id: str
    name: str
    status: str
    progress: float
    start_time: str
    end_time: Optional[str] = None
    agent_count: int
    metric_count: int
    overall_score: Optional[float] = None
    iterations: int


@router.get("/")
@router.get("")
async def get_evaluations():
    """Get all evaluation runs with their status and summary."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    try:
        runs = []
        for run_id, run_data in evaluation_runs.items():
            runs.append(
                {
                    "id": run_id,
                    "name": run_data["name"],
                    "status": run_data["status"],
                    "progress": run_data["progress"],
                    "startTime": run_data["start_time"],
                    "endTime": run_data.get("end_time"),
                    "agentCount": run_data["agent_count"],
                    "metricCount": run_data["metric_count"],
                    "overallScore": run_data.get("overall_score"),
                    "iterations": run_data["iterations"],
                }
            )

        return {
            "status": "success",
            "data": {
                "runs": runs,
                "summary": {
                    "total": len(runs),
                    "active": len([r for r in runs if r["status"] == "running"]),
                    "completed": len([r for r in runs if r["status"] == "completed"]),
                    "failed": len([r for r in runs if r["status"] == "failed"]),
                },
            },
        }
    except Exception as e:
        logger.error(f"Error fetching evaluations: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching evaluations: {str(e)}"
        )


@router.post("/")
@router.post("")
async def create_evaluation(config: EvaluationConfigRequest):
    """Create and start a new evaluation run."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    try:
        # Generate unique evaluation ID
        eval_id = str(uuid.uuid4())

        # Load crews for evaluation
        crews_to_evaluate = []
        agents_to_evaluate = []

        # Get discovered crews from the main application
        from crewai_playground.server import discovered_crews

        for crew_id in config.crew_ids:
            try:
                # Find the crew info from discovered crews
                crew_info = None
                for discovered_crew in discovered_crews:
                    if discovered_crew.get("id") == crew_id:
                        crew_info = discovered_crew
                        break

                if not crew_info:
                    logger.warning(f"Crew {crew_id} not found in discovered crews")
                    continue

                # Load the crew from its path
                crew_path = crew_info.get("path")
                if crew_path:
                    from pathlib import Path

                    crew_path_obj = Path(crew_path)  # Convert string to Path object
                    logger.info(f"Loading crew from path: {crew_path_obj}")
                    loaded_crew_data = load_crew_from_module(crew_path_obj)
                    if loaded_crew_data and len(loaded_crew_data) > 0:
                        crew_instance = loaded_crew_data[0]  # Get the crew instance
                        crews_to_evaluate.append(crew_instance)
                        logger.info(f"Loaded crew instance: {crew_instance}")
                        # Extract agents from crew
                        if hasattr(crew_instance, "agents"):
                            crew_agents = crew_instance.agents
                            logger.info(
                                f"Found {len(crew_agents)} agents in crew {crew_id}: {[getattr(agent, 'role', 'Unknown') for agent in crew_agents]}"
                            )
                            agents_to_evaluate.extend(crew_agents)
                        else:
                            logger.warning(f"Crew {crew_id} has no 'agents' attribute")
                    else:
                        logger.warning(f"Failed to load crew data from {crew_path_obj}")

            except Exception as e:
                logger.warning(f"Failed to load crew {crew_id}: {str(e)}")
                continue

        # If no agents found, we cannot run real evaluations
        if not agents_to_evaluate:
            logger.warning(
                "No real agents found from crews - real evaluations require actual CrewAI agents"
            )
            raise HTTPException(
                status_code=400,
                detail="No real agents found in the selected crews. Real CrewAI evaluations require crews with actual agents. Please ensure your crews are properly configured with agents.",
            )

        # Create evaluation run record
        run_data = {
            "id": eval_id,
            "name": config.name,
            "status": "pending",
            "progress": 0.0,
            "start_time": datetime.datetime.now().isoformat(),
            "end_time": None,
            "agent_count": len(agents_to_evaluate),
            "metric_count": (
                len(config.metric_categories) if config.metric_categories else 6
            ),
            "overall_score": None,
            "iterations": config.iterations,
            "config": {
                "crew_ids": config.crew_ids,
                "metric_categories": config.metric_categories,
                "aggregation_strategy": config.aggregation_strategy,
                "test_inputs": config.test_inputs,
            },
            "agents": [
                {
                    "id": str(
                        agent.get("id")
                        if isinstance(agent, dict)
                        else getattr(agent, "id", "unknown")
                    ),
                    "role": (
                        agent.get("role")
                        if isinstance(agent, dict)
                        else getattr(agent, "role", "Unknown Role")
                    ),
                    "goal": (
                        agent.get("goal")
                        if isinstance(agent, dict)
                        else getattr(agent, "goal", "")
                    ),
                    "backstory": (
                        agent.get("backstory")
                        if isinstance(agent, dict)
                        else getattr(agent, "backstory", "")
                    ),
                }
                for agent in agents_to_evaluate
            ],
        }

        evaluation_runs[eval_id] = run_data

        # Start evaluation in background thread
        evaluation_thread = threading.Thread(
            target=run_evaluation_sync_in_background,
            args=(eval_id, agents_to_evaluate, config),
            daemon=True,
        )
        evaluation_thread.start()

        return {
            "status": "success",
            "data": {
                "evaluation_id": eval_id,
                "message": f"Evaluation '{config.name}' started successfully",
            },
        }

    except Exception as e:
        logger.error(f"Error creating evaluation: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating evaluation: {str(e)}"
        )


@router.get("/metrics")
async def get_available_metrics():
    """Get list of available evaluation metrics."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    try:
        metrics = [
            {
                "id": "goal_alignment",
                "name": "Goal Alignment",
                "description": "Evaluates how well the agent's output aligns with the given goal",
            },
            {
                "id": "semantic_quality",
                "name": "Semantic Quality",
                "description": "Assesses the semantic quality and coherence of the agent's output",
            },
            {
                "id": "reasoning_efficiency",
                "name": "Reasoning Efficiency",
                "description": "Measures the efficiency of the agent's reasoning process",
            },
            {
                "id": "tool_selection",
                "name": "Tool Selection",
                "description": "Evaluates the appropriateness of tool selection and usage",
            },
            {
                "id": "parameter_extraction",
                "name": "Parameter Extraction",
                "description": "Assesses the accuracy of parameter extraction for tool calls",
            },
            {
                "id": "tool_invocation",
                "name": "Tool Invocation",
                "description": "Evaluates the correctness of tool invocation and usage",
            },
        ]

        aggregation_strategies = [
            {
                "id": "simple_average",
                "name": "Simple Average",
                "description": "Equal weight to all tasks",
            },
            {
                "id": "weighted_by_complexity",
                "name": "Weighted by Complexity",
                "description": "Weight by task complexity",
            },
            {
                "id": "best_performance",
                "name": "Best Performance",
                "description": "Use best scores across tasks",
            },
            {
                "id": "worst_performance",
                "name": "Worst Performance",
                "description": "Use worst scores across tasks",
            },
        ]

        return {
            "status": "success",
            "data": {
                "metrics": metrics,
                "aggregation_strategies": aggregation_strategies,
            },
        }
    except Exception as e:
        logger.error(f"Error fetching available metrics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching available metrics: {str(e)}"
        )


@router.get("/{evaluation_id}")
async def get_evaluation(evaluation_id: str):
    """Get detailed information about a specific evaluation run."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    if evaluation_id not in evaluation_runs:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    try:
        run_data = evaluation_runs[evaluation_id]
        results = evaluation_results.get(evaluation_id, {})

        return {"status": "success", "data": {"run": run_data, "results": results}}
    except Exception as e:
        logger.error(f"Error fetching evaluation {evaluation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching evaluation: {str(e)}"
        )


@router.get("/{evaluation_id}/results")
async def get_evaluation_results(evaluation_id: str):
    """Get detailed results for a completed evaluation."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    if evaluation_id not in evaluation_runs:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    try:
        run_data = evaluation_runs[evaluation_id]
        if run_data["status"] != "completed":
            return {
                "status": "success",
                "data": {
                    "message": f"Evaluation is {run_data['status']}",
                    "progress": run_data["progress"],
                },
            }

        results = evaluation_results.get(evaluation_id, {})

        return {
            "status": "success",
            "data": {
                "evaluation_id": evaluation_id,
                "results": results,
                "summary": {
                    "overall_score": run_data.get("overall_score"),
                    "agent_count": run_data["agent_count"],
                    "metric_count": run_data["metric_count"],
                    "iterations": run_data["iterations"],
                },
            },
        }
    except Exception as e:
        logger.error(f"Error fetching evaluation results {evaluation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching evaluation results: {str(e)}"
        )


@router.delete("/{evaluation_id}")
async def delete_evaluation(evaluation_id: str):
    """Delete an evaluation run and its results."""
    if not EVALUATION_AVAILABLE:
        raise HTTPException(status_code=501, detail="Evaluation features not available")

    if evaluation_id not in evaluation_runs:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    try:
        # Stop active evaluation if running
        if evaluation_id in active_evaluations:
            # Cancel the evaluation task if possible
            del active_evaluations[evaluation_id]

        # Remove from storage
        del evaluation_runs[evaluation_id]
        if evaluation_id in evaluation_results:
            del evaluation_results[evaluation_id]

        return {
            "status": "success",
            "data": {"message": "Evaluation deleted successfully"},
        }
    except Exception as e:
        logger.error(f"Error deleting evaluation {evaluation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting evaluation: {str(e)}"
        )


def run_evaluation_sync_in_background(
    eval_id: str, agents: List, config: EvaluationConfigRequest
):
    """Run evaluation synchronously in a background thread using working sync crew execution."""
    try:
        # Update status to running
        evaluation_runs[eval_id]["status"] = "running"
        evaluation_runs[eval_id]["progress"] = 10.0

        # Ensure we have agents for evaluation
        if not agents:
            raise ValueError(
                f"No agents provided for evaluation {eval_id}. Real agents are required."
            )

        # Get discovered crews from the main application
        from crewai_playground.server import discovered_crews

        # Find crews that contain these agents
        crews_to_evaluate = []
        for crew_id in config.crew_ids:
            crew_info = next(
                (c for c in discovered_crews if c.get("id") == crew_id), None
            )
            if crew_info:
                try:
                    from pathlib import Path

                    crew_path_obj = Path(crew_info.get("path"))
                    loaded_crew_data = load_crew_from_module(crew_path_obj)
                    if loaded_crew_data and len(loaded_crew_data) > 0:
                        crew_instance = loaded_crew_data[0]
                        crews_to_evaluate.append(crew_instance)
                except Exception as e:
                    logger.warning(
                        f"Failed to load crew {crew_id} for evaluation: {str(e)}"
                    )
                    continue

        if not crews_to_evaluate:
            raise ValueError(
                f"No crews could be loaded for evaluation {eval_id}. Real crews are required."
            )

        # Extract the actual agent instances from the loaded crews
        crew_agents = []
        for crew in crews_to_evaluate:
            if hasattr(crew, "agents"):
                crew_agents.extend(crew.agents)

        # Create evaluator with the actual agent instances from the crews
        try:
            evaluator = create_default_evaluator(agents=crew_agents)
            active_evaluations[eval_id] = evaluator
        except Exception as e:
            logger.error(f"Failed to create evaluator: {str(e)}")
            raise

        # Update progress
        evaluation_runs[eval_id]["progress"] = 30.0

        # Run crews synchronously (the working approach)
        for i, crew in enumerate(crews_to_evaluate):
            logger.info(
                f"Running crew {i+1}/{len(crews_to_evaluate)} for evaluation {eval_id}"
            )

            # Execute crew synchronously with test inputs
            test_inputs = config.test_inputs or {
                "industry": "AI",
                "current_year": "2024",
            }
            crew.kickoff(inputs=test_inputs)

            # Update progress
            progress = 30.0 + (50.0 * (i + 1) / len(crews_to_evaluate))
            evaluation_runs[eval_id]["progress"] = progress

        # Aggregate results for this iteration
        iteration_results = evaluator.get_agent_evaluation(
            include_evaluation_feedback=True,
        )

        logger.info(f"Iteration results for {eval_id}: {iteration_results}")

        # Calculate overall score from iteration results
        overall_scores = []
        if iteration_results and hasattr(iteration_results, "values"):
            for agent_result in iteration_results.values():
                if (
                    hasattr(agent_result, "overall_score")
                    and agent_result.overall_score is not None
                ):
                    overall_scores.append(agent_result.overall_score)
                elif isinstance(agent_result, dict) and "overall_score" in agent_result:
                    overall_scores.append(agent_result["overall_score"])

        overall_score = (
            sum(overall_scores) / len(overall_scores) if overall_scores else None
        )

        # Store results in the expected format
        agent_results = (
            {
                agent_id: (
                    result.model_dump()
                    if hasattr(result, "model_dump")
                    else (result.__dict__ if hasattr(result, "__dict__") else result)
                )
                for agent_id, result in iteration_results.items()
            }
            if iteration_results
            else {}
        )

        # Store results (agent_results is already in the correct format)
        evaluation_results[eval_id] = {
            "agent_results": agent_results,
            "summary": {
                "overall_score": overall_score,
                "total_agents": len(agent_results),
                "aggregation_strategy": config.aggregation_strategy,
            },
        }

        # Update final status
        evaluation_runs[eval_id]["status"] = "completed"
        evaluation_runs[eval_id]["progress"] = 100.0
        evaluation_runs[eval_id]["end_time"] = datetime.datetime.now().isoformat()
        evaluation_runs[eval_id]["overall_score"] = overall_score

        # Clean up
        if eval_id in active_evaluations:
            del active_evaluations[eval_id]

        logger.info(
            f"Evaluation {eval_id} completed successfully with {len(agent_results)} agent results"
        )

    except Exception as e:
        logger.error(f"Error running evaluation {eval_id}: {str(e)}")
        evaluation_runs[eval_id]["status"] = "failed"
        evaluation_runs[eval_id]["progress"] = 0.0
        evaluation_runs[eval_id]["end_time"] = datetime.datetime.now().isoformat()

        # Clean up
        if eval_id in active_evaluations:
            del active_evaluations[eval_id]
