import { useEffect, useState } from "react";
import { FileCode2, Cpu, Globe, Network, Shield, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageHeader } from "@/components/PageHeader";
import { CodeBlock } from "@/components/CodeBlock";
import { getInstances, generateTerraform } from "@/lib/api";
import { toast } from "sonner";

const RESOURCE_OPTS = [
  { key: "ec2", label: "EC2 Instances", icon: Cpu },
  { key: "dns", label: "Route53 DNS (A)", icon: Globe },
  { key: "srv", label: "Route53 SRV", icon: Network },
  { key: "sg", label: "Security Groups", icon: Shield },
];

const inputCls =
  "bg-[#09090B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2";

export default function Generator() {
  const [instances, setInstances] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [resources, setResources] = useState(new Set(["ec2", "dns", "srv", "sg"]));
  const [zoneId, setZoneId] = useState("Z1234567890ABC");
  const [defaultAmi, setDefaultAmi] = useState("ami-0c55b159cbfafe1f0");
  const [defaultType, setDefaultType] = useState("t3.medium");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getInstances().then(setInstances).catch(() => {});
  }, []);

  const toggleSet = (set, setter, key) => {
    const next = new Set(set);
    next.has(key) ? next.delete(key) : next.add(key);
    setter(next);
  };

  const allSelected = instances.length > 0 && selected.size === instances.length;
  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(instances.map((i) => i.id)));

  const generate = async () => {
    if (resources.size === 0) {
      toast.error("Select at least one resource type");
      return;
    }
    setBusy(true);
    try {
      const res = await generateTerraform({
        instance_ids: selected.size ? Array.from(selected) : null,
        resources: Array.from(resources),
        output_format: "both",
        zone_id: zoneId,
        default_ami: defaultAmi,
        default_instance_type: defaultType,
      });
      setResult(res);
      toast.success(`Generated ${res.resource_count} resources`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader title="Terraform Generator" subtitle="Turn inventory into reviewable IaC" />
      <div className="p-8 grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-6">
        {/* Config panel */}
        <div className="space-y-5">
          <Panel title="Resources">
            <div className="space-y-2.5">
              {RESOURCE_OPTS.map((r) => {
                const Icon = r.icon;
                return (
                  <label key={r.key} data-testid={`resource-${r.key}`} className="flex items-center gap-3 cursor-pointer group">
                    <Checkbox
                      checked={resources.has(r.key)}
                      onCheckedChange={() => toggleSet(resources, setResources, r.key)}
                      className="border-white/25 data-[state=checked]:bg-orange-500 data-[state=checked]:border-orange-500 rounded-sm"
                    />
                    <Icon className="h-4 w-4 text-zinc-500 group-hover:text-orange-500 transition-colors duration-150" />
                    <span className="text-sm text-zinc-300">{r.label}</span>
                  </label>
                );
              })}
            </div>
          </Panel>

          <Panel title="Defaults">
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-zinc-400">Route53 Zone ID</Label>
                <Input data-testid="zone-id" value={zoneId} onChange={(e) => setZoneId(e.target.value)} className={inputCls} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-zinc-400">Default AMI</Label>
                <Input data-testid="default-ami" value={defaultAmi} onChange={(e) => setDefaultAmi(e.target.value)} className={inputCls} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-zinc-400">Default Instance Type</Label>
                <Input data-testid="default-type" value={defaultType} onChange={(e) => setDefaultType(e.target.value)} className={inputCls} />
              </div>
            </div>
          </Panel>

          <Panel
            title={
              <div className="flex items-center justify-between">
                <span>Instances ({selected.size ? selected.size : "all"})</span>
                <button data-testid="toggle-all" onClick={toggleAll} className="text-[11px] text-orange-500 hover:underline font-normal">
                  {allSelected ? "Clear" : "Select all"}
                </button>
              </div>
            }
          >
            <div className="max-h-64 overflow-y-auto space-y-1.5 pr-1">
              {instances.length === 0 ? (
                <p className="text-xs text-zinc-600">No instances. Import inventory first.</p>
              ) : (
                instances.map((i) => (
                  <label key={i.id} className="flex items-center gap-2.5 cursor-pointer py-1">
                    <Checkbox
                      checked={selected.has(i.id)}
                      onCheckedChange={() => toggleSet(selected, setSelected, i.id)}
                      className="border-white/25 data-[state=checked]:bg-orange-500 data-[state=checked]:border-orange-500 rounded-sm"
                    />
                    <span className="text-xs font-mono text-zinc-300 truncate">
                      {i.instance_name || i.host || "unnamed"}
                    </span>
                  </label>
                ))
              )}
            </div>
            <p className="text-[11px] text-zinc-600 mt-2">Leave unselected to include all.</p>
          </Panel>

          <Button
            data-testid="generate-tf-button"
            onClick={generate}
            disabled={busy}
            className="w-full bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2 h-11"
          >
            <Zap className="h-4 w-4" /> {busy ? "Generating…" : "Generate Terraform"}
          </Button>
        </div>

        {/* Output panel */}
        <div>
          {result ? (
            <div className="space-y-3">
              <div className="text-xs text-zinc-500 font-mono">
                {result.resource_count} terraform resources generated
              </div>
              <Tabs defaultValue="hcl">
                <TabsList className="bg-[#18181B] border border-[#27272A] rounded-sm">
                  <TabsTrigger value="hcl" data-testid="tab-hcl" className="data-[state=active]:bg-orange-500 data-[state=active]:text-white rounded-sm">
                    main.tf (HCL)
                  </TabsTrigger>
                  <TabsTrigger value="json" data-testid="tab-json" className="data-[state=active]:bg-orange-500 data-[state=active]:text-white rounded-sm">
                    main.tf.json
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="hcl" className="mt-3">
                  <CodeBlock code={result.hcl || ""} language="hcl" filename="main.tf" />
                </TabsContent>
                <TabsContent value="json" className="mt-3">
                  <CodeBlock code={result.json || ""} language="json" filename="main.tf.json" />
                </TabsContent>
              </Tabs>
            </div>
          ) : (
            <div className="h-full min-h-[400px] flex flex-col items-center justify-center border border-dashed border-white/10 rounded-sm">
              <FileCode2 className="h-10 w-10 text-zinc-700 mb-3" strokeWidth={1.25} />
              <p className="text-sm text-zinc-500">Configure and generate to preview Terraform</p>
              <p className="text-xs text-zinc-600 mt-1">Output in HCL and Terraform JSON</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const Panel = ({ title, children }) => (
  <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-4">
    <h3 className="font-head font-semibold text-xs uppercase tracking-wider text-zinc-400 mb-3">{title}</h3>
    {children}
  </div>
);
