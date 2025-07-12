import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { Button } from "~/components/ui/button";
import { useChatStore } from "~/lib/store";
import { Card } from "~/components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Layout } from "../components/Layout";
import {
  MessageSquare,
  Zap,
  Moon,
  Sun,
  Wrench,
  Share2,
  LayoutDashboard,
  BookUser,
  BotMessageSquare,
  Network,
  Clock,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";

export function meta() {
  return [
    { title: "CrewAI - Dashboard" },
    { name: "description", content: "Dashboard for CrewAI Playground" },
  ];
}

interface StatCardProps {
  title: string;
  value: number;
  icon: React.ElementType;
  isLoading?: boolean;
}

function StatCard({
  title,
  value,
  icon: Icon,
  isLoading = false,
}: StatCardProps) {
  return (
    <div className="bg-card p-6 rounded-lg shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-muted-foreground">{title}</h3>
        <Icon className="h-6 w-6 text-muted-foreground" />
      </div>
      {isLoading ? (
        <Skeleton className="h-10 w-16" />
      ) : (
        <p className="text-4xl font-bold">{value}</p>
      )}
    </div>
  );
}

interface FlowData {
  id: string;
  name: string;
  status: string;
  start_time: number;
}

interface ActiveFlowCardProps {
  flow: FlowData;
}

function ActiveFlowCard({ flow }: ActiveFlowCardProps) {
  const statusIcons: Record<string, React.ReactNode> = {
    running: <Clock className="h-5 w-5 text-blue-500" />,
    failed: <AlertCircle className="h-5 w-5 text-red-500" />,
    completed: <CheckCircle2 className="h-5 w-5 text-green-500" />,
  };

  const getStatusIcon = (status: string): React.ReactNode => {
    return statusIcons[status] || <Clock className="h-5 w-5 text-gray-500" />;
  };

  return (
    <Card className="p-4">
      <div className="flex justify-between items-center">
        <div className="flex items-center">
          <Network className="h-5 w-5 mr-2 text-primary" />
          <span className="font-medium">{flow.name}</span>
        </div>
        <div className="flex items-center">
          {getStatusIcon(flow.status)}
          <span className="ml-2 text-sm capitalize">{flow.status}</span>
        </div>
      </div>
    </Card>
  );
}

interface TraceData {
  id: string;
  crew_name?: string;
  timestamp: number;
}

interface RecentTraceCardProps {
  trace: TraceData;
}

function RecentTraceCard({ trace }: RecentTraceCardProps) {
  const date = new Date(trace.timestamp * 1000).toLocaleString();

  return (
    <Card className="p-4">
      <div className="flex justify-between items-center">
        <div>
          <div className="font-medium">{trace.crew_name || "Unknown Crew"}</div>
          <div className="text-sm text-muted-foreground">{date}</div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => window.open(`/traces/${trace.id}`, "_blank")}
        >
          View
        </Button>
      </div>
    </Card>
  );
}

export default function Dashboard() {
  const [isLoading, setIsLoading] = useState(true);
  interface DashboardData {
    counts: {
      crews: number;
      tools: number;
      flows: number;
    };
    recent_traces: TraceData[];
    active_flows: FlowData[];
  }

  const [dashboardData, setDashboardData] = useState<DashboardData>({
    counts: {
      crews: 0,
      tools: 0,
      flows: 0,
    },
    recent_traces: [],
    active_flows: [],
  });

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setIsLoading(true);
        const response = await fetch("/api/dashboard");
        const result = await response.json();

        if (result.status === "success" && result.data) {
          setDashboardData(result.data);
        } else {
          console.error("Failed to fetch dashboard data:", result);
        }
      } catch (error) {
        console.error("Error fetching dashboard data:", error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchDashboardData();

    // Set up a refresh interval (every 30 seconds)
    const intervalId = setInterval(fetchDashboardData, 30000);

    // Clean up the interval on component unmount
    return () => clearInterval(intervalId);
  }, []);

  return (
    <Layout>
      <h1 className="text-2xl font-bold mb-8">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <StatCard
          title="Crews"
          value={dashboardData.counts.crews}
          icon={BookUser}
          isLoading={isLoading}
        />
        <StatCard
          title="Tools"
          value={dashboardData.counts.tools}
          icon={Wrench}
          isLoading={isLoading}
        />
        <StatCard
          title="Flows"
          value={dashboardData.counts.flows}
          icon={Network}
          isLoading={isLoading}
        />
      </div>

      {dashboardData.active_flows.length > 0 && (
        <div className="mt-12">
          <h2 className="text-2xl font-bold mb-6">Active Flows</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {dashboardData.active_flows.map((flow) => (
              <ActiveFlowCard key={flow.id} flow={flow} />
            ))}
          </div>
        </div>
      )}

      {dashboardData.recent_traces.length > 0 && (
        <div className="mt-12">
          <h2 className="text-2xl font-bold mb-6">Recent Activity</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {dashboardData.recent_traces.map((trace) => (
              <RecentTraceCard key={trace.id} trace={trace} />
            ))}
          </div>
        </div>
      )}

      <div className="mt-12">
        <h2 className="text-2xl font-bold mb-6">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          <Button
            className="h-auto py-6 flex flex-col items-center justify-center gap-2"
            onClick={() => (window.location.href = "/chat")}
          >
            <BotMessageSquare className="h-8 w-8" />
            <span>Start Chat</span>
          </Button>
          <Button
            className="h-auto py-6 flex flex-col items-center justify-center gap-2"
            onClick={() => (window.location.href = "/kickoff")}
          >
            <Zap className="h-8 w-8" />
            <span>Kickoff Crew</span>
          </Button>
          <Button
            className="h-auto py-6 flex flex-col items-center justify-center gap-2"
            onClick={() => (window.location.href = "/flow")}
          >
            <Network className="h-8 w-8" />
            <span>Run Flow</span>
          </Button>
          <Button
            className="h-auto py-6 flex flex-col items-center justify-center gap-2"
            onClick={() => (window.location.href = "/tools")}
          >
            <Wrench className="h-8 w-8" />
            <span>Explore Tools</span>
          </Button>
        </div>
      </div>
    </Layout>
  );
}
