import type { Route } from "./+types/home";
import ChatLayout from "./chat";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "CrewAI Playground" },
    { name: "description", content: "Welcome to CrewAI Playground" },
  ];
}

export default function Home() {
  return <ChatLayout />;
}
