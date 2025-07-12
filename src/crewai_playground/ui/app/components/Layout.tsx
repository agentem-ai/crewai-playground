import React from "react";
import { useLocation, useNavigate } from "react-router";
import { Button } from "~/components/ui/button";
import { useChatStore } from "~/lib/store";
import {
  LayoutDashboard,
  BotMessageSquare,
  Zap,
  Wrench,
  Network,
  Moon,
  Sun,
} from "lucide-react";

function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  const navItems = [
    { icon: LayoutDashboard, label: "Dashboard", path: "/" },
    { icon: BotMessageSquare, label: "Chat", path: "/chat" },
    { icon: Zap, label: "Crews", path: "/kickoff" },
    { icon: Wrench, label: "Tools", path: "/tools" },
    { icon: Network, label: "Flows", path: "/flow" },
  ];

  return (
    <aside className="w-64 flex-shrink-0 border-r bg-background p-4 flex flex-col">
      <div className="flex items-center mb-8">
        <h2 className="text-2xl font-bold">CrewAI Playground</h2>
      </div>
      <nav className="flex flex-col space-y-2">
        {navItems.map((item, index) => (
          <Button
            key={index}
            variant={location.pathname === item.path ? "secondary" : "ghost"}
            className="justify-start"
            onClick={() => navigate(item.path)}
          >
            <item.icon className="mr-2 h-5 w-5" />
            {item.label}
          </Button>
        ))}
      </nav>
    </aside>
  );
}

interface LayoutProps {
  children: React.ReactNode;
  rightSidebar?: React.ReactNode;
}

export function Layout({ children, rightSidebar }: LayoutProps) {
  const { isDarkMode, toggleDarkMode } = useChatStore();

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex flex-col flex-1">
        <header className="py-4 px-8 border-b bg-background">
          <div className="flex items-center justify-end">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleDarkMode}
              className="h-8 w-8"
            >
              {isDarkMode ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Moon className="h-4 w-4" />
              )}
            </Button>
          </div>
        </header>
        <main className="flex-grow p-8 overflow-auto flex">
          <div className="flex-1">{children}</div>
          {rightSidebar && (
            <div className="w-72 border-l bg-background p-4">
              {rightSidebar}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
