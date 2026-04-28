import { useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { PanelLeftOpen } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { useSession } from "../stores/session";
import { getSessionMessages } from "../lib/api";
import type { ChatMessage } from "../stores/session";

export function AppShell() {
  const navigate = useNavigate();
  const setSession = useSession((s) => s.setSession);
  const loadMessages = useSession((s) => s.loadMessages);
  const resetConversation = useSession((s) => s.resetConversation);
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    if (typeof window === "undefined") return true;
    return window.innerWidth > 800;
  });

  const handleSelectSession = async (id: string) => {
    const rows = await getSessionMessages(id);
    const messages: ChatMessage[] = rows.map((r) => ({
      id: r.id,
      role: r.role,
      text: r.content,
    }));
    setSession(id);
    loadMessages(messages);
    navigate("/chat");
  };

  const handleNewChat = () => {
    resetConversation();
    navigate("/chat");
  };

  return (
    <div className={`app ${sidebarOpen ? "sidebar-open" : "sidebar-collapsed"}`}>
      <Sidebar
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onToggle={() => setSidebarOpen((open) => !open)}
      />
      {sidebarOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close sidebar"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <main className="main">
        {!sidebarOpen && (
          <button
            type="button"
            className="sidebar-open-btn"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
            title="Open sidebar"
          >
            <PanelLeftOpen size={18} />
          </button>
        )}
        <Outlet />
      </main>
    </div>
  );
}
