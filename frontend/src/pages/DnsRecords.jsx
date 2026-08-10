import { useEffect, useState, useMemo } from "react";
import { Globe, Network, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageHeader } from "@/components/PageHeader";
import { getInstances } from "@/lib/api";

export default function DnsRecords() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    getInstances().then(setItems).catch(() => {});
  }, []);

  const dns = useMemo(() => {
    const rows = [];
    items.forEach((i) =>
      (i.dns_records || []).forEach((d) =>
        rows.push({ record: d, host: i.host, name: i.instance_name, role: i.instance_role })
      )
    );
    return rows.filter((r) => r.record.toLowerCase().includes(q.toLowerCase()));
  }, [items, q]);

  const srv = useMemo(() => {
    const rows = [];
    items.forEach((i) =>
      (i.srv_records || []).forEach((s) =>
        rows.push({ record: s, host: i.host, port: i.port, name: i.instance_name })
      )
    );
    return rows.filter((r) => r.record.toLowerCase().includes(q.toLowerCase()));
  }, [items, q]);

  return (
    <div>
      <PageHeader title="DNS & SRV Records" subtitle="All resolvable records mapped to hosts" />
      <div className="p-8 space-y-4">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
          <Input
            data-testid="dns-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter records..."
            className="pl-9 bg-[#18181B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2"
          />
        </div>

        <Tabs defaultValue="dns">
          <TabsList className="bg-[#18181B] border border-[#27272A] rounded-sm">
            <TabsTrigger value="dns" data-testid="tab-dns" className="data-[state=active]:bg-orange-500 data-[state=active]:text-white rounded-sm gap-2">
              <Globe className="h-4 w-4" /> DNS ({dns.length})
            </TabsTrigger>
            <TabsTrigger value="srv" data-testid="tab-srv" className="data-[state=active]:bg-orange-500 data-[state=active]:text-white rounded-sm gap-2">
              <Network className="h-4 w-4" /> SRV ({srv.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="dns" className="mt-4">
            <RecordTable
              rows={dns}
              cols={["Record", "Type", "Resolves To", "Instance", "Role"]}
              render={(r) => (
                <>
                  <td className="px-4 py-2.5 font-mono text-orange-400">{r.record}</td>
                  <td className="px-4 py-2.5 font-mono text-zinc-500">A</td>
                  <td className="px-4 py-2.5 font-mono text-zinc-300">{r.host || "—"}</td>
                  <td className="px-4 py-2.5 text-zinc-300">{r.name || "—"}</td>
                  <td className="px-4 py-2.5 font-mono text-zinc-500">{r.role || "—"}</td>
                </>
              )}
            />
          </TabsContent>
          <TabsContent value="srv" className="mt-4">
            <RecordTable
              rows={srv}
              cols={["SRV Record", "Type", "Target Host", "Port", "Instance"]}
              render={(r) => (
                <>
                  <td className="px-4 py-2.5 font-mono text-orange-400">{r.record}</td>
                  <td className="px-4 py-2.5 font-mono text-zinc-500">SRV</td>
                  <td className="px-4 py-2.5 font-mono text-zinc-300">{r.host || "—"}</td>
                  <td className="px-4 py-2.5 font-mono text-zinc-300">{r.port || "—"}</td>
                  <td className="px-4 py-2.5 text-zinc-300">{r.name || "—"}</td>
                </>
              )}
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

const RecordTable = ({ rows, cols, render }) => (
  <div className="bg-[#18181B] border border-[#27272A] rounded-sm overflow-hidden">
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-[#27272A] text-left text-[11px] uppercase tracking-wider text-zinc-500">
          {cols.map((c) => <th key={c} className="px-4 py-3 font-medium">{c}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr><td colSpan={cols.length} className="px-4 py-12 text-center text-zinc-600">No records found.</td></tr>
        ) : (
          rows.map((r, i) => (
            <tr key={i} className="border-b border-[#27272A]/60 hover:bg-white/5 transition-colors duration-150">
              {render(r)}
            </tr>
          ))
        )}
      </tbody>
    </table>
  </div>
);
