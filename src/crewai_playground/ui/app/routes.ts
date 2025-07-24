import { type RouteConfig } from "@react-router/dev/routes";

export default [
  { index: true, file: "routes/dashboard.tsx" },
  { path: "chat", file: "routes/chat.tsx" },
  { path: "crews", file: "routes/crews.tsx" },
  { path: "crews/traces", file: "routes/crews.traces.tsx" },
  { path: "crews/evals", file: "routes/crews.evals.tsx" },
  { path: "tools", file: "routes/tools.tsx" },
  { path: "flows", file: "routes/flows.tsx" },
  { path: "flows/traces", file: "routes/flows.traces.tsx" },
] satisfies RouteConfig;
