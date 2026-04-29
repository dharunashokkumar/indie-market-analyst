import { NavLink } from "react-router-dom";
import {
  Activity,
  BarChart3,
  BellDot,
  CalendarDays,
  Clock4,
  History,
  Search,
  Sunrise,
} from "lucide-react";

const ITEMS = [
  { to: "/intraday/pre-market", label: "Pre-market", icon: Sunrise },
  { to: "/intraday/pre-open", label: "Pre-open", icon: BellDot },
  { to: "/intraday", label: "Live", icon: Activity, end: true },
  { to: "/intraday/last-hour", label: "Last hour", icon: Clock4 },
  { to: "/intraday/post-market", label: "Post-market", icon: History },
  { to: "/intraday/symbol", label: "Symbol", icon: Search },
  { to: "/intraday/update", label: "Update", icon: BarChart3 },
  { to: "/intraday/weekend", label: "Weekend", icon: CalendarDays },
];

export function IntradayNav() {
  return (
    <nav className="intraday-nav" aria-label="Intraday modes">
      {ITEMS.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className="intraday-nav-link"
          >
            <Icon size={14} />
            <span>{item.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
