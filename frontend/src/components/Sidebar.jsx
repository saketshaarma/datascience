import { NavLink } from "react-router-dom";
import { LayoutDashboard, Server, Globe, FileCode2, Boxes, Users, LogOut, Ship } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, id: "nav-dashboard" },
  { to: "/inventory", label: "Inventory", icon: Server, id: "nav-inventory" },
  { to: "/dns", label: "DNS & SRV", icon: Globe, id: "nav-dns" },
  { to: "/generator", label: "Terraform", icon: FileCode2, id: "nav-generator" },
  { to: "/kubernetes", label: "Kubernetes", icon: Ship, id: "nav-kubernetes" },
  { to: "/team", label: "Team", icon: Users, id: "nav-team" },
];

export const Sidebar = () => {
  const { user, signOut } = useAuth();

  return (
    <aside className="fixed left-0 top-0 h-screen w-60 border-r border-[#27272A] bg-[#09090B] flex flex-col z-30">
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-[#27272A]">
        <div className="h-8 w-8 rounded-sm bg-orange-500 flex items-center justify-center">
          <Boxes className="h-5 w-5 text-black" strokeWidth={2} />
        </div>
        <div className="leading-tight">
          <div className="font-head font-bold text-sm text-white">InfraForge</div>
          <div className="text-[10px] text-zinc-500 font-mono tracking-wide">AWS INVENTORY</div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {nav.map((n) => {
          const Icon = n.icon;
          return (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              data-testid={n.id}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-sm text-sm transition-colors duration-150 ${
                  isActive
                    ? "bg-orange-500/10 text-orange-400 border-l-2 border-orange-500"
                    : "text-zinc-400 hover:text-white hover:bg-white/5 border-l-2 border-transparent"
                }`
              }
            >
              <Icon className="h-4 w-4" strokeWidth={1.75} />
              {n.label}
            </NavLink>
          );
        })}
      </nav>

      <div className="px-3 py-4 border-t border-[#27272A]">
        <div className="flex items-center gap-3 px-2 mb-3">
          <div className="h-8 w-8 rounded-sm bg-orange-500/15 border border-orange-500/30 flex items-center justify-center text-orange-400 font-head font-semibold text-sm uppercase">
            {(user?.name || user?.email || "?")[0]}
          </div>
          <div className="min-w-0 leading-tight">
            <div className="text-xs text-white truncate">{user?.name || "User"}</div>
            <div className="text-[10px] text-zinc-500 font-mono truncate">{user?.role}</div>
          </div>
        </div>
        <button
          data-testid="logout-button"
          onClick={signOut}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-sm text-sm text-zinc-400 hover:text-white hover:bg-white/5 transition-colors duration-150"
        >
          <LogOut className="h-4 w-4" strokeWidth={1.75} /> Sign out
        </button>
      </div>
    </aside>
  );
};
