import { useEffect, useState, useCallback } from "react";
import {
  Server, HardDrive, ShieldCheck, Globe, FileText, Search, RefreshCw, Radar, Cloud, Network, Tag as TagIcon, Database, Play, Square,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  HoverCard, HoverCardContent, HoverCardTrigger,
} from "@/components/ui/hover-card";
import { PageHeader } from "@/components/PageHeader";
import { getTagOptions, discoverAws, instanceAction } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const TYPES = [
  { kind: "ec2_instance", label: "EC2 Instances", icon: Server },
  { kind: "security_group", label: "Security Groups", icon: ShieldCheck },
  { kind: "ebs_volume", label: "Volumes", icon: HardDrive },
  { kind: "rds_db", label: "RDS Databases", icon: Database },
  { kind: "route53_zone", label: "Route53 Zones", icon: Globe },
  { kind: "a_record", label: "A Records", icon: FileText },
];

const sourceColor = (s) => ({
  inventory: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  kubernetes: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  db_config: "bg-green-500/15 text-green-400 border-green-500/30",
  aws: "bg-purple-500/15 text-purple-400 border-purple-500/30",
}[s] || "bg-zinc-500/15 text-zinc-400 border-zinc-500/30");

const D = (r, k) => {
  const v = (r.details || {})[k];
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
};

const COLUMNS = {
  ec2_instance: [
    { label: "Name", render: (r) => r.name },
    { label: "Instance ID", render: (r) => D(r, "instance_id") },
    { label: "Private IP", render: (r) => D(r, "private_ip") },
    { label: "Type", render: (r) => D(r, "instance_type") },
    { label: "Region", render: (r) => r.region || "—" },
  ],
  security_group: [
    { label: "Name", render: (r) => r.name },
    { label: "Ports", render: (r) => D(r, "ports") },
    { label: "VPC / Cluster", render: (r) => D(r, "vpc") !== "—" ? D(r, "vpc") : D(r, "cluster") },
    { label: "Region", render: (r) => r.region || "—" },
  ],
  ebs_volume: [
    { label: "Name", render: (r) => r.name },
    { label: "Device", render: (r) => D(r, "device_name") },
    { label: "Size (GB)", render: (r) => D(r, "size_gb") },
    { label: "Type", render: (r) => D(r, "volume_type") },
    { label: "Attached To", render: (r) => D(r, "attached_to") },
  ],
  rds_db: [
    { label: "Name", render: (r) => r.name },
    { label: "Status", render: (r) => r.status || "—" },
    { label: "Region", render: (r) => r.region || "—" },
  ],
  route53_zone: [
    { label: "Zone", render: (r) => r.name },
    { label: "Records", render: (r) => D(r, "record_count") },
    { label: "Private", render: (r) => (r.details?.private ? "yes" : "no") },
    { label: "Region", render: (r) => r.region || "—" },
  ],
  a_record: [
    { label: "Record", render: (r) => r.name },
    { label: "Type", render: (r) => D(r, "type") },
    { label: "Value", render: (r) => D(r, "value") },
    { label: "TTL", render: (r) => D(r, "ttl") },
    { label: "Zone", render: (r) => D(r, "zone") },
  ],
};

const GENERIC_COLS = [
  { label: "Name", render: (r) => r.name },
  { label: "ID", render: (r) => r.id },
  { label: "Type", render: (r) => r.details?.resource_type || r.kind },
  { label: "Status", render: (r) => r.status || "—" },
  { label: "Region", render: (r) => r.region || "—" },
];

const prettyKind = (k) =>
  (TYPES.find((t) => t.kind === k)?.label) ||
  String(k).replace(/[:_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function Dashboard() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tagKeys, setTagKeys] = useState([]);
  const [tagValues, setTagValues] = useState({});
  const [key, setKey] = useState("__all__");
  const [value, setValue] = useState("__all__");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeKind, setActiveKind] = useState("ec2_instance");
  const [actioning, setActioning] = useState(null);

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
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadTags(); run("__all__", "__all__"); }, [loadTags, run]);

  const onKeyChange = (k) => { setKey(k); setValue("__all__"); };

  const doAction = async (r, action) => {
    setActioning(r.id);
    try {
      const res = await instanceAction(r.id, action);
      toast.success(`${r.name}: ${action} → ${res.state}`);
      setTimeout(() => run(key, value), 1200);
    } catch (e) {
      toast.error(e?.response?.data?.detail || `Failed to ${action} instance`);
    } finally { setActioning(null); }
  };

  const s = data || { total: 0, resources: [], mode: "demo", region: "-", account_id: "-" };
  const countOf = (kind) => s.resources.filter((r) => r.kind === kind).length;
  // Known type cards + any additional resource kinds returned by live discovery.
  const extraKinds = Array.from(new Set(s.resources.map((r) => r.kind))).filter(
    (k) => !TYPES.some((t) => t.kind === k)
  );
  const typeCards = [
    ...TYPES,
    ...extraKinds.map((k) => ({ kind: k, label: prettyKind(k), icon: Network })),
  ];
  const rows = s.resources.filter((r) => r.kind === activeKind);
  const cols = COLUMNS[activeKind] || GENERIC_COLS;
  const showActions = activeKind === "ec2_instance" && s.mode === "live" && isAdmin;

  return (
    <div>
      <PageHeader
        title="Discovery Dashboard"
        subtitle="Select a resource type, filter by tags, hover for details"
        actions={
          <Badge variant="outline" className={`rounded-sm font-mono text-[11px] gap-1.5 ${s.mode === "live" ? "bg-green-500/15 text-green-400 border-green-500/30" : "bg-yellow-500/15 text-yellow-400 border-yellow-500/30"}`}>
            <Cloud className="h-3 w-3" /> {s.mode === "live" ? "LIVE AWS" : "DEMO MODE"}
          </Badge>
        }
      />

      <div className="p-8 space-y-6">
        {/* type selector */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {typeCards.map((t) => {
            const Icon = t.icon;
            const active = activeKind === t.kind;
            return (
              <button
                key={t.kind}
                data-testid={`type-${t.kind}`}
                onClick={() => setActiveKind(t.kind)}
                className={`text-left rounded-sm border p-4 transition-all duration-150 ${
                  active
                    ? "bg-orange-500/10 border-orange-500 ring-1 ring-orange-500/40"
                    : "bg-[#18181B] border-[#27272A] hover:border-white/25 hover:-translate-y-0.5"
                }`}
              >
                <div className="flex items-center justify-between">
                  <Icon className={`h-4 w-4 ${active ? "text-orange-400" : "text-zinc-500"}`} />
                  <span className="font-head font-bold text-2xl text-white tabular-nums">{countOf(t.kind)}</span>
                </div>
                <div className={`text-xs mt-2 ${active ? "text-orange-300" : "text-zinc-400"}`}>{t.label}</div>
              </button>
            );
          })}
        </div>

        {/* filter bar */}
        <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-4 flex flex-wrap items-end gap-3">
          <div className="flex items-center gap-2 text-orange-500 mr-2">
            <Radar className="h-5 w-5" />
            <span className="font-head font-semibold text-sm text-white">Filter by tag</span>
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
            {s.total} total · region <span className="text-zinc-300">{s.region}</span> · acct <span className="text-zinc-300">{s.account_id}</span>
          </div>
        </div>

        {/* type table */}
        <div className="bg-[#18181B] border border-[#27272A] rounded-sm overflow-hidden">
          <div className="overflow-x-auto max-h-[540px]">
            <table className="w-full text-sm" data-testid="discovery-table">
              <thead className="sticky top-0 bg-[#18181B]">
                <tr className="border-b border-[#27272A] text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  {cols.map((c) => <th key={c.label} className="px-4 py-3 font-medium">{c.label}</th>)}
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium text-right">Tags</th>
                  {showActions && <th className="px-4 py-3 font-medium text-right">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr><td colSpan={cols.length + 2 + (showActions ? 1 : 0)} className="px-4 py-16 text-center text-zinc-600">No {typeCards.find((t) => t.kind === activeKind)?.label || activeKind} for this filter.</td></tr>
                ) : rows.map((r, i) => (
                  <tr key={i} data-testid={`res-row-${i}`} className="border-b border-[#27272A]/60 hover:bg-white/5 transition-colors duration-150">
                    {cols.map((c, ci) => (
                      <td key={c.label} className="px-4 py-2.5 font-mono text-zinc-300">
                        {ci === 0 ? (
                          <HoverCard openDelay={80} closeDelay={40}>
                            <HoverCardTrigger asChild>
                              <span data-testid={`res-hover-${i}`} className="text-white font-medium cursor-help underline decoration-dotted decoration-zinc-600 underline-offset-4">
                                {c.render(r)}
                              </span>
                            </HoverCardTrigger>
                            <HoverCardContent side="right" align="start" className="w-80 bg-[#0d0d0f] border-[#27272A] text-white rounded-sm p-0 overflow-hidden">
                              <ResourcePopup r={r} />
                            </HoverCardContent>
                          </HoverCard>
                        ) : c.render(r)}
                      </td>
                    ))}
                    <td className="px-4 py-2.5"><Badge variant="outline" className={`rounded-sm font-mono text-[11px] ${sourceColor(r.source)}`}>{r.source}</Badge></td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-1 justify-end max-w-xs">
                        {Object.entries(r.tags || {}).slice(0, 3).map(([k, v]) => (
                          <span key={k} className="text-[10px] font-mono bg-white/5 text-zinc-400 rounded-sm px-1.5 py-0.5">{k}={v}</span>
                        ))}
                        {Object.keys(r.tags || {}).length > 3 && <span className="text-[10px] text-zinc-600">+{Object.keys(r.tags).length - 3}</span>}
                      </div>
                    </td>
                    {showActions && (
                      <td className="px-4 py-2.5">
                        <div className="flex items-center justify-end gap-1.5">
                          {String(r.status).toLowerCase() === "running" ? (
                            <Button data-testid={`ec2-stop-${r.id}`} size="sm" disabled={actioning === r.id}
                              onClick={() => doAction(r, "stop")}
                              className="h-7 gap-1 bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 hover:bg-yellow-500/25 rounded-sm text-xs">
                              <Square className="h-3 w-3" /> Stop
                            </Button>
                          ) : (
                            <Button data-testid={`ec2-start-${r.id}`} size="sm" disabled={actioning === r.id}
                              onClick={() => doAction(r, "start")}
                              className="h-7 gap-1 bg-green-500/15 text-green-400 border border-green-500/30 hover:bg-green-500/25 rounded-sm text-xs">
                              <Play className="h-3 w-3" /> Start
                            </Button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

const ResourcePopup = ({ r }) => {
  const Icon = TYPES.find((t) => t.kind === r.kind)?.icon || Cloud;
  return (
    <div>
      <div className="flex items-center gap-2.5 px-4 py-3 bg-orange-500/10 border-b border-[#27272A]">
        <div className="h-8 w-8 rounded-sm bg-orange-500/15 flex items-center justify-center">
          <Icon className="h-4 w-4 text-orange-400" />
        </div>
        <div className="min-w-0">
          <div className="font-head font-semibold text-white text-sm truncate">{r.name}</div>
          <div className="text-[10px] font-mono text-zinc-500">{r.id}</div>
        </div>
      </div>
      <div className="p-4 space-y-3">
        <div className="grid grid-cols-2 gap-x-3 gap-y-2">
          {Object.entries(r.details || {}).map(([k, v]) => (
            <div key={k}>
              <div className="text-[10px] uppercase tracking-wider text-zinc-600 font-mono">{k.replace(/_/g, " ")}</div>
              <div className="text-xs text-zinc-200 font-mono truncate" title={String(v)}>
                {v === null || v === undefined || v === "" ? "—" : Array.isArray(v) ? v.join(", ") : String(v)}
              </div>
            </div>
          ))}
        </div>
        <div className="pt-2 border-t border-[#27272A]">
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-zinc-600 font-mono mb-1.5">
            <TagIcon className="h-3 w-3" /> Tags
          </div>
          <div className="flex flex-wrap gap-1">
            {Object.keys(r.tags || {}).length === 0 ? (
              <span className="text-xs text-zinc-600">none</span>
            ) : Object.entries(r.tags).map(([k, v]) => (
              <span key={k} className="text-[10px] font-mono bg-white/5 text-zinc-300 rounded-sm px-1.5 py-0.5">{k}={v}</span>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-between pt-1">
          <Badge variant="outline" className={`rounded-sm font-mono text-[10px] ${sourceColor(r.source)}`}>{r.source}</Badge>
          <span className="text-[10px] font-mono text-zinc-500">{r.region}</span>
        </div>
      </div>
    </div>
  );
};
