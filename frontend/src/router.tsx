import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ChatPage } from "./pages/ChatPage";
import { MarketChartPage } from "./pages/MarketChartPage";
import { OptionsPage } from "./pages/OptionsPage";
import { FNOPage } from "./pages/FNOPage";
import { DashboardsPage } from "./pages/DashboardsPage";
import { StrategyPage } from "./pages/StrategyPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: "chat", element: <ChatPage /> },
      { path: "dashboards", element: <DashboardsPage /> },
      { path: "strategy", element: <StrategyPage /> },
      { path: "market", element: <MarketChartPage /> },
      { path: "options", element: <OptionsPage /> },
      { path: "fno", element: <FNOPage /> },
      { path: "runs", element: <Navigate to="/dashboards?tab=backtests" replace /> },
    ],
  },
]);
