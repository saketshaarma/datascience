import { useEffect, useState, useCallback } from "react";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
} from "recharts";
import {
  Server, HardDrive, ShieldCheck, Globe, Database, Search, RefreshCw, Radar, Cloud,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/PageHeader";
import { getTagOptions, discoverAws } from "@/lib/api";
import { toast } from "sonner";

const COLORS = ["#F97316", "#3B82F6", "#22C55E", "#EAB308", "#A855F7", "#EC4899"];

const KIND_META = {
  ec2_instance: { label: "EC2", icon: Server },
  ebs_volume: { label: "EBS Volume", icon: HardDrive },
  security_group: { label: "Security Group", icon: ShieldCheck },
  route53_record: { label: "Route53", icon: Globe },
  rds_instance: { label: "RDS / DB", icon: Database },
};

const kindLabel = (k) => KIND_META[k]?.label || k;
const kindIcon = (k) => KIND_META[k]?.icon || Cloud;

const sourceColor = (s) => ({
  inventory: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  kubernetes: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  db_config: "bg-green-500/15 text-green-400 border-green-500/30",
  aws: "bg-purple-500/15 text-purple-400 border-purple-500/30",
}[s] || "bg-zinc-500/15 text-zinc-400 border-zinc-500/30");

export default function Dashboard() {
  const [tagKeys, setTagKeys] = useState([]);
  const [tagValues, setTagValues] = useState({});
  const [key, setKey] = useState("__all__");
  const [value, setValue] = useState("__all__");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadTags = useCallback(async () => {
    try {
      const t = await getTagOptions();
      setTagKeys(t.keys || []);
      setTagValues(t.values || {});
    } catch (_) {}
  }, []);

  const run = useCallback(async (k, v) => {
    setLoading(true);
    try {
      const body = {};
      if (k && k !== "__all__") {
        body.tag_key = k;
        if (v && v !== "__all__") body.tag_value = v;
      }
      setData(await discoverAws(body));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Discovery failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTags(); run("__all__", "__all__"); }, [loadTags, run]);

  const onKeyChange = (k) => { setKey(k); setValue("__all__"); };
  const s = data || { total: 0, by_kind: [], by_source: [], resources: [], mode: "demo", region: "-", account_id: "-" };

  return (
    <div>
      <PageHeader
        title="Discovery Dashboard"
        subtitle="AWS resources discovered by tags across all sections"
        actions={
          <Badge variant="outline" className={`rounded-sm font-mono text-[11px] gap-1.5 ${s.mode === "live" ? "bg-green-500/15 text-green-400 border-green-500/30" : "bg-yellow-500/15 text-yellow-400 border-yellow-500/30"}`}>
            <Cloud className="h-3 w-3" /> {s.mode === "live" ? "LIVE AWS" : "DEMO MODE"}
          </Badge>
        }
      />

      <div className="p-8 space-y-6">
        {/* discovery control bar */}
        <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-4 flex flex-wrap items-end gap-3">
          <div className="flex items-center gap-2 text-orange-500 mr-2">
            <Radar className="h-5 w-5" />
            <span className="font-head font-semibold text-sm text-white">Discover by tag</span>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono">Tag key</label>
            <Select value={key} onValueChange={onKeyChange}>
              <SelectTrigger data-testid="discover-tag-key" className="w-48 bg-[#09090B] border-[#27272A] text-white text-sm rounded-sm"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-[#18181B] border-[#27272A] text-white max-h-72">
                <SelectItem value="__all__">All resources</SelectItem>
                {tagKeys.map((k) => <SelectItem key={k} value={k}>{k}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono">Tag value</label>
            <Select value={value} onValueChange={setValue} disabled={key === "__all__"}>
              <SelectTrigger data-testid="discover-tag-value" className="w-48 bg-[#09090B] border-[#27272A] text-white text-sm rounded-sm disabled:opacity-40"><SelectValue placeholder="Any value" /></SelectTrigger>
              <SelectContent className="bg-[#18181B] border-[#27272A] text-white max-h-72">
                <SelectItem value="__all__">Any value</SelectItem>
                {(tagValues[key] || []).map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button data-testid="discover-run" onClick={() => run(key, value)} disabled={loading}
            className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2 h-10">
            {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            {loading ? "Discovering…" : "Discover"}
          </Button>
          <div className="ml-auto text-xs text-zinc-500 font-mono self-center">
            region <span className="text-zinc-300">{s.region}</span> · account <span className="text-zinc-300">{s.account_id}</span>
          </div>
        </div>

        {/* summary cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <div data-testid="stat-total" className="bg-[#18181B] border border-[#27272A] rounded-sm p-5 animate-fade-up">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-zinc-500 font-mono">Total</span>
              <Cloud className="h-4 w-4 text-orange-500" />
            </div>
            <div className="font-head font-bold text-3xl text-white mt-3 tabular-nums">{s.total}</div>
          </div>
          {["ec2_instance", "ebs_volume", "security_group", "route53_record", "rds_instance"].map((k) => {
            const Icon = kindIcon(k);
            const v = s.by_kind.find((x) => x.name === k)?.value || 0;
            return (
              <div key={k} data-testid={`stat-${k}`} className="bg-[#18181B] border border-[#27272A] rounded-sm p-5 animate-fade-up">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-wider text-zinc-500 font-mono">{kindLabel(k)}</span>
                  <Icon className="h-4 w-4 text-zinc-500" />
                </div>
                <div className="font-head font-bold text-3xl text-white mt-3 tabular-nums">{v}</div>
              </div>
            );
          })}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4">
          {/* by source pie */}
          <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-5">
            <h3 className="font-head font-semibold text-sm text-white mb-4">By Source</h3>
            {s.by_source.length === 0 ? (
              <div className="h-[220px] flex items-center justify-center text-sm text-zinc-600">No resources</div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={s.by_source} dataKey="value" nameKey="name" innerRadius={45} outerRadius={80} paddingAngle={2} stroke="#09090B">
                      {s.by_source.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: "#09090B", border: "1px solid #27272A", borderRadius: "2px", fontSize: "12px", fontFamily: "JetBrains Mono" }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3">
                  {s.by_source.map((it, i) => (
                    <div key={it.name} className="flex items-center gap-2 text-xs text-zinc-400">
                      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} />
                      <span className="font-mono">{it.name}</span><span className="text-zinc-600">{it.value}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* resource table */}
          <div className="bg-[#18181B] border border-[#27272A] rounded-sm overflow-hidden">
            <div className="overflow-x-auto max-h-[520px]">
              <table className="w-full text-sm" data-testid="discovery-table">
                <thead className="sticky top-0 bg-[#18181B]">
                  <tr className="border-b border-[#27272A] text-left text-[11px] uppercase tracking-wider text-zinc-500">
                    <th className="px-4 py-3 font-medium">Kind</th>
                    <th className="px-4 py-3 font-medium">Name / ID</th>
                    <th className="px-4 py-3 font-medium">Region</th>
                    <th className="px-4 py-3 font-medium">Source</th>
                    <th className="px-4 py-3 font-medium">Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {s.resources.length === 0 ? (
                    <tr><td colSpan={5} className="px-4 py-16 text-center text-zinc-600">No resources discovered for this filter.</td></tr>
                  ) : s.resources.map((r, i) => {
                    const Icon = kindIcon(r.kind);
                    return (
                      <tr key={i} className="border-b border-[#27272A]/60 hover:bg-white/5 transition-colors duration-150">
                        <td className="px-4 py-2.5">
                          <span className="flex items-center gap-2 text-zinc-300"><Icon className="h-4 w-4 text-orange-500" /> {kindLabel(r.kind)}</span>
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="text-white">{r.name}</div>
                          <div className="text-[11px] text-zinc-600 font-mono">{r.id}</div>
                        </td>
                        <td className="px-4 py-2.5 font-mono text-zinc-400">{r.region || "—"}</td>
                        <td className="px-4 py-2.5"><Badge variant="outline" className={`rounded-sm font-mono text-[11px] ${sourceColor(r.source)}`}>{r.source}</Badge></td>
                        <td className="px-4 py-2.5">
                          <div className="flex flex-wrap gap-1 max-w-md">
                            {Object.entries(r.tags || {}).slice(0, 4).map(([k, v]) => (
                              <span key={k} className="text-[10px] font-mono bg-white/5 text-zinc-400 rounded-sm px-1.5 py-0.5">{k}={v}</span>
                            ))}
                            {Object.keys(r.tags || {}).length > 4 && <span className="text-[10px] text-zinc-600">+{Object.keys(r.tags).length - 4}</span>}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
