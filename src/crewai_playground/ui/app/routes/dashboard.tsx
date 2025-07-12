import { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { Button } from "~/components/ui/button";
import { useChatStore } from "~/lib/store";
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
} from "lucide-react";

export function meta() {
  return [
    { title: "CrewAI - Dashboard" },
    { name: "description", content: "Dashboard for CrewAI Playground" },
  ];
}

function Sidebar() {
  const navigate = useNavigate();

  const navItems = [
    { icon: LayoutDashboard, label: "Dashboard", path: "/" },
    { icon: BotMessageSquare, label: "Chat Mode", path: "/chat" },
    { icon: Zap, label: "Kickoff Mode", path: "/kickoff" },
    { icon: Wrench, label: "Tools", path: "/tools" },
    { icon: Network, label: "Flow Mode", path: "/flow" },
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
            variant="ghost"
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

function StatCard({ title, value, icon: Icon }) {
  return (
    <div className="bg-card p-6 rounded-lg shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-muted-foreground">{title}</h3>
        <Icon className="h-6 w-6 text-muted-foreground" />
      </div>
      <p className="text-4xl font-bold">{value}</p>
    </div>
  );
}

export default function Dashboard() {
  const { crews, isDarkMode, toggleDarkMode } = useChatStore();
  const [tools, setTools] = useState([]);
  const [flows, setFlows] = useState([]);

  useEffect(() => {
    // Mock fetching tools and flows
    // Replace with actual API calls
    setTools(["Tool 1", "Tool 2", "Tool 3"]);
    setFlows(["Flow 1", "Flow 2"]);
  }, []);

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex flex-col flex-1">
        <header className="py-4 px-8 border-b bg-background">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold">Dashboard</h1>
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
        <main className="flex-grow p-8 overflow-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <StatCard title="Crews" value={crews.length} icon={BookUser} />
            <StatCard title="Tools" value={tools.length} icon={Wrench} />
            <StatCard title="Flows" value={flows.length} icon={Network} />
          </div>

          <div className="mt-12">
            <h2 className="text-2xl font-bold mb-6">Quick Actions</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
              {/* Quick action cards from previous design can be adapted here */}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
