import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { Server, Globe, Network, Cpu, ArrowRight, Boxes } from "lucide-react";
import { getStats } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";

const COLORS = ["#F97316", "#3B82F6", "#22C55E", "#EAB308", "#A855F7", "#EC4899"];

const StatCard = ({ icon: Icon, label, value, testid }) => (
  <div
    data-testid={testid}
    className="bg-[#18181B] border border-[#27272A] rounded-sm p-5 animate-fade-up"
  >
    <div className="flex items-center justify-between">
      <span className="text-xs uppercase tracking-wider text-zinc-500 font-mono">{label}</span>
      <Icon className="h-4 w-4 text-orange-500" strokeWidth={1.75} />
    </div>
    <div className="font-head font-bold text-3xl text-white mt-3 tabular-nums">{value}</div>
  </div>
);

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    getStats().then(setStats).catch(() => {});
  }, []);

  const s = stats || { total_hosts: 0, total_dns: 0, total_srv: 0, role_breakdown: [], type_breakdown: [] };

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Infrastructure inventory overview" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Server} label="Hosts / Instances" value={s.total_hosts} testid="stat-hosts" />
          <StatCard icon={Globe} label="DNS Records" value={s.total_dns} testid="stat-dns" />
          <StatCard icon={Network} label="SRV Records" value={s.total_srv} testid="stat-srv" />
          <StatCard icon={Cpu} label="Instance Roles" value={s.role_breakdown.length} testid="stat-roles" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-5">
            <h3 className="font-head font-semibold text-sm text-white mb-4">Instance Role Breakdown</h3>
            {s.role_breakdown.length === 0 ? (
              <EmptyChart />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={s.role_breakdown}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={2}
                    stroke="#09090B"
                  >
                    {s.role_breakdown.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
            )}
            <Legend items={s.role_breakdown} />
          </div>

          <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-5">
            <h3 className="font-head font-semibold text-sm text-white mb-4">EC2 Instance Types</h3>
            {s.type_breakdown.length === 0 ? (
              <EmptyChart />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={s.type_breakdown} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272A" horizontal={false} />
                  <XAxis type="number" stroke="#52525b" fontSize={11} />
                  <YAxis type="category" dataKey="name" stroke="#a1a1aa" fontSize={11} width={90} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                  <Bar dataKey="value" fill="#F97316" radius={[0, 2, 2, 0]} barSize={18} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div
          onClick={() => navigate("/generator")}
          data-testid="dashboard-generate-cta"
          className="group cursor-pointer bg-[#18181B] border border-[#27272A] hover:border-orange-500/50 rounded-sm p-6 flex items-center justify-between transition-colors duration-150"
        >
          <div className="flex items-center gap-4">
            <div className="h-11 w-11 rounded-sm bg-orange-500/10 flex items-center justify-center">
              <Boxes className="h-5 w-5 text-orange-500" strokeWidth={1.75} />
            </div>
            <div>
              <div className="font-head font-semibold text-white">Generate Terraform</div>
              <div className="text-xs text-zinc-500">
                Turn your inventory into EC2, Route53 & Security Group config
              </div>
            </div>
          </div>
          <ArrowRight className="h-5 w-5 text-zinc-600 group-hover:text-orange-500 group-hover:translate-x-1 transition-all duration-150" />
        </div>
      </div>
    </div>
  );
}

const tooltipStyle = {
  background: "#09090B",
  border: "1px solid #27272A",
  borderRadius: "2px",
  fontSize: "12px",
  fontFamily: "JetBrains Mono, monospace",
};

const Legend = ({ items }) => (
  <div className="flex flex-wrap gap-x-4 gap-y-2 mt-4">
    {items.map((it, i) => (
      <div key={it.name} className="flex items-center gap-2 text-xs text-zinc-400">
        <span className="h-2.5 w-2.5 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} />
        <span className="font-mono">{it.name}</span>
        <span className="text-zinc-600">{it.value}</span>
      </div>
    ))}
  </div>
);

const EmptyChart = () => (
  <div className="h-[260px] flex items-center justify-center border border-dashed border-white/10 rounded-sm">
    <span className="text-sm text-zinc-600">No data yet. Import your inventory.</span>
  </div>
);
