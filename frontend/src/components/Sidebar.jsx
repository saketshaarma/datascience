import { NavLink } from "react-router-dom";
import { LayoutDashboard, Server, Globe, FileCode2, Boxes } from "lucide-react";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, id: "nav-dashboard" },
  { to: "/inventory", label: "Inventory", icon: Server, id: "nav-inventory" },
  { to: "/dns", label: "DNS & SRV", icon: Globe, id: "nav-dns" },
  { to: "/generator", label: "Terraform", icon: FileCode2, id: "nav-generator" },
];

export const Sidebar = () => {
  return (
    <aside className="fixed left-0 top-0 h-screen w-60 border-r border-[#27272A] bg-[#09090B] flex flex-col z-30">
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-[#27272A]">
        <div className="h-8 w-8 rounded-sm bg-orange-500 flex items-center justify-center">
          <Boxes className="h-5 w-5 text-black" strokeWidth={2} />
        </div>
        <div className="leading-tight">
          <div className="font-head font-bold text-sm text-white">InfraForge</div>
          <div className="text-[10px] text-zinc-500 font-mono tracking-wide">
            AWS INVENTORY
          </div>
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

      <div className="px-5 py-4 border-t border-[#27272A]">
        <div className="text-[10px] text-zinc-600 font-mono">
          Source of truth for
          <br /> infrastructure metadata
        </div>
      </div>
    </aside>
  );
};
