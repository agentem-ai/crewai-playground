import React from "react";
import { useNavigate, useLocation } from "react-router";
import { Play, Activity, BarChart3 } from "lucide-react";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

interface KickoffNavigationProps {
  crewId?: string;
}

export function KickoffNavigation({ crewId }: KickoffNavigationProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const path = location.pathname;

  // Navigation items for the kickoff section
  const navigationItems = [
    {
      name: "Execution",
      path: crewId ? `/crews?crewId=${crewId}` : "/crews",
      icon: <Play className="h-4 w-4" />,
      isActive: path === "/crews",
    },
    {
      name: "Traces",
      path: `/crews/traces?crewId=${crewId}`,
      icon: <Activity className="h-4 w-4" />,
      isActive: path.includes("/crews/traces"),
    },
    {
      name: "Evaluations",
      path: `/crews/evals?crewId=${crewId}`,
      icon: <BarChart3 className="h-4 w-4" />,
      isActive: path.includes("/crews/evals"),
    },
  ];

  return (
    <div className="border rounded-lg p-1 flex mb-4 bg-muted/30">
      {navigationItems.map((item) => (
        <Button
          key={item.name}
          variant={item.isActive ? "default" : "ghost"}
          size="sm"
          className={cn(
            "flex-1 flex items-center justify-center gap-2",
            item.isActive ? "shadow-sm" : "hover:bg-muted/50"
          )}
          onClick={() => navigate(item.path)}
          disabled={!crewId && item.name !== "Execution"}
        >
          {item.icon}
          {item.name}
        </Button>
      ))}
    </div>
  );
}
