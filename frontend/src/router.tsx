import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ChatPage } from "./pages/ChatPage";
import { MarketChartPage } from "./pages/MarketChartPage";
import { OptionsPage } from "./pages/OptionsPage";
import { FNOPage } from "./pages/FNOPage";
import { DashboardsPage } from "./pages/DashboardsPage";
import { StrategyPage } from "./pages/StrategyPage";
import { IntradayPage } from "./pages/Intraday/IntradayPage";
import { LastHourPage } from "./pages/Intraday/LastHourPage";
import { PostMarketPage } from "./pages/Intraday/PostMarketPage";
import { PreMarketPage } from "./pages/Intraday/PreMarketPage";
import { PreOpenPage } from "./pages/Intraday/PreOpenPage";
import { SettingsPage as IntradaySettingsPage } from "./pages/Intraday/SettingsPage";
import { SymbolPage } from "./pages/Intraday/SymbolPage";
import { UpdatePage } from "./pages/Intraday/UpdatePage";
import { WeekendPage } from "./pages/Intraday/WeekendPage";

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
      { path: "intraday", element: <IntradayPage /> },
      { path: "intraday/pre-market", element: <PreMarketPage /> },
      { path: "intraday/pre-open", element: <PreOpenPage /> },
      { path: "intraday/last-hour", element: <LastHourPage /> },
      { path: "intraday/post-market", element: <PostMarketPage /> },
      { path: "intraday/symbol", element: <SymbolPage /> },
      { path: "intraday/symbol/:ticker", element: <SymbolPage /> },
      { path: "intraday/update", element: <UpdatePage /> },
      { path: "intraday/weekend", element: <WeekendPage /> },
      { path: "intraday/settings", element: <IntradaySettingsPage /> },
      { path: "runs", element: <Navigate to="/dashboards?tab=backtests" replace /> },
    ],
  },
]);
