import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink } from "react-router-dom";
import {
  Activity,
  BarChart3,
  LineChart,
  MessageSquare,
  PanelLeftClose,
  Plus,
} from "lucide-react";
import {
  deleteSession,
  listSessions,
  searchSessions,
  type SessionSummary,
} from "../lib/api";
import { useSession } from "../stores/session";
import { SessionList } from "./SessionList";
import { ThemeToggle } from "./ThemeToggle";

export function Sidebar({
  onSelectSession,
  onNewChat,
  onToggle,
}: {
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onToggle: () => void;
}) {
  const sessions = useSession((s) => s.sessions);
  const setSessions = useSession((s) => s.setSessions);
  const setLoading = useSession((s) => s.setSessionsLoading);
  const loading = useSession((s) => s.sessionsLoading);
  const activeId = useSession((s) => s.sessionId);
  const removeLocal = useSession((s) => s.removeSessionLocally);

  const [query, setQuery] = useState("");
  const [searchRows, setSearchRows] = useState<SessionSummary[] | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listSessions();
      setSessions(rows);
    } finally {
      setLoading(false);
    }
  }, [setLoading, setSessions]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setSearchRows(null);
      return;
    }
    const timer = setTimeout(async () => {
      const matches = await searchSessions(q);
      const ids = new Set(matches.map((m) => m.session_id));
      setSearchRows(sessions.filter((s) => ids.has(s.id)));
    }, 220);
    return () => clearTimeout(timer);
  }, [query, sessions]);

  const displayed = useMemo(
    () => (searchRows !== null ? searchRows : sessions),
    [searchRows, sessions]
  );

  const handleDelete = async (id: string) => {
    const ok = await deleteSession(id);
    if (ok) removeLocal(id);
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="brand">
          <div className="brand-dot" />
          indie-market-analyst
        </div>
        <button
          type="button"
          className="sidebar-toggle-btn"
          onClick={onToggle}
          aria-label="Close sidebar"
          title="Close sidebar"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>

      <div className="sidebar-actions">
        <button
          type="button"
          className="new-chat-btn"
          onClick={() => {
            onNewChat();
            refresh();
          }}
        >
          <Plus size={14} />
          New
        </button>
      </div>

      <nav className="sidebar-nav">
        <NavLink to="/chat" className="sidebar-nav-link">
          <MessageSquare size={14} />
          Chat
        </NavLink>
        <NavLink to="/dashboards" className="sidebar-nav-link">
          <BarChart3 size={14} />
          Dashboards
        </NavLink>
        <NavLink to="/strategy" className="sidebar-nav-link">
          <LineChart size={14} />
          Strategy
        </NavLink>
        <NavLink to="/intraday" className="sidebar-nav-link">
          <Activity size={14} />
          Intraday
        </NavLink>
      </nav>

      <div className="sidebar-search">
        <input
          type="text"
          placeholder="Search history…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <SessionList
        sessions={displayed}
        activeId={activeId}
        onSelect={onSelectSession}
        onDelete={handleDelete}
        loading={loading}
      />

      <div className="sidebar-footer">
        <ThemeToggle />
        <div className="version">v0.1.0</div>
      </div>
    </aside>
  );
}
