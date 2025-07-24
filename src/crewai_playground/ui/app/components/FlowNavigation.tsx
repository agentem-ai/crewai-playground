import React from "react";
import { useNavigate, useLocation } from "react-router";
import { Play, Activity } from "lucide-react";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

interface FlowNavigationProps {
  flowId?: string;
}

export function FlowNavigation({ flowId }: FlowNavigationProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const path = location.pathname;

  // Navigation items for the flow section
  const navigationItems = [
    {
      name: "Execution",
      path: flowId ? `/flows?flowId=${flowId}` : "/flows",
      icon: <Play className="h-4 w-4" />,
      isActive: path === "/flows",
    },
    {
      name: "Traces",
      path: flowId ? `/flows/traces?flowId=${flowId}` : "/flows/traces",
      icon: <Activity className="h-4 w-4" />,
      isActive: path.includes("/flows/traces"),
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
        >
          {item.icon}
          {item.name}
        </Button>
      ))}
    </div>
  );
}
