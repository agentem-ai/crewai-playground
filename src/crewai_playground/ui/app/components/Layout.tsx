import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { Button } from "~/components/ui/button";
import { useChatStore } from "~/lib/store";
import {
  LayoutDashboard,
  BotMessageSquare,
  Zap,
  Wrench,
  Network,
  BarChart3,
  Moon,
  Sun,
  ChevronLeft,
  ChevronRight,
  Menu,
  X,
} from "lucide-react";

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const navItems = [
    { icon: LayoutDashboard, label: "Dashboard", path: "/" },
    { icon: BotMessageSquare, label: "Chat", path: "/chat" },
    { icon: Zap, label: "Crews", path: "/crews" },
    { icon: Wrench, label: "Tools", path: "/tools" },
    { icon: Network, label: "Flows", path: "/flows" },
  ];

  return (
    <aside
      className={`
        ${isCollapsed ? "w-16" : "sm:w-32 md:w-40 lg:w-48"} 
        flex-shrink-0 border-r bg-background flex flex-col transition-all duration-300 ease-in-out relative
      `}
    >
      {/* Toggle Button */}
      <Button
        variant="ghost"
        size="icon"
        onClick={onToggle}
        className="absolute -right-3 top-6 z-10 h-6 w-6 rounded-full border bg-background shadow-md hover:shadow-lg transition-all duration-200"
      >
        {isCollapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </Button>

      <div className={`p-4 ${isCollapsed ? "px-2" : ""}`}>
        {/* Header */}
        <div className="flex items-center mb-8">
          {isCollapsed ? (
            <div className="flex justify-center w-full">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                <Zap className="h-4 w-4 text-white" />
              </div>
            </div>
          ) : (
            <h2 className="text-xl font-bold">CrewAI Playground</h2>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex flex-col space-y-2">
          {navItems.map((item, index) => (
            <Button
              key={index}
              variant={location.pathname === item.path ? "secondary" : "ghost"}
              className={`
                ${isCollapsed ? "justify-center px-2" : "justify-start"} 
                transition-all duration-200 hover:scale-105
                ${location.pathname === item.path ? "shadow-md" : ""}
              `}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                navigate(item.path);
              }}
              title={isCollapsed ? item.label : undefined}
            >
              <item.icon className={`h-5 w-5 ${isCollapsed ? "" : "mr-2"}`} />
              {!isCollapsed && item.label}
            </Button>
          ))}
        </nav>
      </div>
    </aside>
  );
}

interface LayoutProps {
  children: React.ReactNode;
  rightSidebar?: React.ReactNode;
}

export function Layout({ children, rightSidebar }: LayoutProps) {
  const { isDarkMode, toggleDarkMode } = useChatStore();
  
  // Persist sidebar collapse states in localStorage
  const [isLeftSidebarCollapsed, setIsLeftSidebarCollapsed] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('crewai-left-sidebar-collapsed');
      return saved ? JSON.parse(saved) : false;
    }
    return false;
  });
  
  const [isRightSidebarCollapsed, setIsRightSidebarCollapsed] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('crewai-right-sidebar-collapsed');
      return saved ? JSON.parse(saved) : false;
    }
    return false;
  });

  // Update localStorage when collapse states change
  const toggleLeftSidebar = () => {
    const newState = !isLeftSidebarCollapsed;
    setIsLeftSidebarCollapsed(newState);
    if (typeof window !== 'undefined') {
      localStorage.setItem('crewai-left-sidebar-collapsed', JSON.stringify(newState));
    }
  };

  const toggleRightSidebar = () => {
    const newState = !isRightSidebarCollapsed;
    setIsRightSidebarCollapsed(newState);
    if (typeof window !== 'undefined') {
      localStorage.setItem('crewai-right-sidebar-collapsed', JSON.stringify(newState));
    }
  };

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar
        isCollapsed={isLeftSidebarCollapsed}
        onToggle={toggleLeftSidebar}
      />
      <div className="flex flex-col flex-1">
        <header className="sm:py-1 md:py-1 lg:py-2 px-4 border-b bg-background">
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
        <main className="flex-grow p-2 overflow-auto flex gap-2">
          <div className="flex-1">{children}</div>
          {rightSidebar && (
            <div
              className={`
                ${
                  isRightSidebarCollapsed
                    ? "w-16"
                    : "w-full sm:w-40 md:w-48 lg:w-64 max-w-96"
                } 
                border-l bg-background transition-all duration-300 ease-in-out relative
              `}
            >
              {/* Right Sidebar Toggle Button */}
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleRightSidebar}
                className="absolute -left-3 top-4 z-10 h-6 w-6 rounded-full border bg-background shadow-md hover:shadow-lg transition-all duration-200"
              >
                {isRightSidebarCollapsed ? (
                  <ChevronLeft className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
              </Button>

              {/* Right Sidebar Content */}
              <div
                className={`${
                  isRightSidebarCollapsed ? "p-2" : "p-4"
                } transition-all duration-300`}
              >
                {isRightSidebarCollapsed ? (
                  <div className="flex flex-col items-center space-y-2 mt-8">
                    <div className="w-8 h-8 bg-gradient-to-br from-green-500 to-teal-600 rounded-lg flex items-center justify-center">
                      <Menu className="h-4 w-4 text-white" />
                    </div>
                  </div>
                ) : (
                  rightSidebar
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
