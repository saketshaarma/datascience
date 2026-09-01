import { useEffect, useState, useCallback } from "react";
import {
  Plus, Save, Zap, Trash2, Server, Boxes, X, Cpu, HardDrive,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageHeader } from "@/components/PageHeader";
import { CodeBlock } from "@/components/CodeBlock";
import {
  listClusters, createCluster, updateCluster, deleteCluster, previewCluster,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const inputCls =
  "bg-[#09090B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2";

const objToLines = (o) => Object.entries(o || {}).map(([k, v]) => `${k}=${v}`).join("\n");
const linesToObj = (s) => {
  const o = {};
  (s || "").split("\n").map((x) => x.trim()).filter(Boolean).forEach((l) => {
    const i = l.indexOf("=");
    if (i > 0) o[l.slice(0, i).trim()] = l.slice(i + 1).trim();
  });
  return o;
};

const template = () => ({
  name: "analytics-cluster",
  aws_region: "ap-south-2",
  vpc_tag: "Pakri-analytics-db-vpc",
  subnet_tag: "Pakri-analytics-db-pvt",
  key_name: "HYD",
  private_zone_name: "ieil.net",
  ami_id: "",
  security_group_tags: { Environment: "Backup", Role: "SRE" },
  instance_tags: {
    Environment: "prod", GroupName: "NM-PakriAnalytics", Business: "BKP-DataScience-Pakri",
    BU: "DataScience", ManagedBy: "Terraform", Owner: "SRE",
    Application: "Kubernates-node", DR: "Yes",
  },
  volume_tags: {
    Environment: "prod", GroupName: "NM-PakriAnalytics", Business: "BKP-DataScience-Pakri",
    BU: "DataScience", ManagedBy: "Terraform", Owner: "SRE",
    Application: "Kubernates-node", DR: "Yes",
  },
  nodes: [
    { hostname: "controller0", instance_type: "t3.medium", root_volume_size: 50 },
    { hostname: "controller1", instance_type: "t3.medium", root_volume_size: 50 },
    { hostname: "controller2", instance_type: "t3.medium", root_volume_size: 50 },
    { hostname: "etcd3", instance_type: "t3.medium", root_volume_size: 50 },
    { hostname: "etcd4", instance_type: "t3.medium", root_volume_size: 50 },
  ],
});

const toForm = (c) => ({
  ...c,
  sg_tags: objToLines(c.security_group_tags),
  inst_tags: objToLines(c.instance_tags),
  vol_tags: objToLines(c.volume_tags),
});

const toPayload = (f) => ({
  name: f.name,
  aws_region: f.aws_region,
  vpc_tag: f.vpc_tag,
  subnet_tag: f.subnet_tag,
  key_name: f.key_name,
  private_zone_name: f.private_zone_name,
  ami_id: f.ami_id || "",
  security_group_tags: linesToObj(f.sg_tags),
  instance_tags: linesToObj(f.inst_tags),
  volume_tags: linesToObj(f.vol_tags),
  nodes: (f.nodes || []).map((n) => ({
    hostname: n.hostname,
    instance_type: n.instance_type,
    root_volume_size: parseInt(n.root_volume_size, 10) || 0,
  })),
  extra: f.extra || {},
});

const Field = ({ label, children }) => (
  <div className="space-y-1.5">
    <Label className="text-xs text-zinc-400">{label}</Label>
    {children}
  </div>
);

export default function Kubernetes() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [clusters, setClusters] = useState([]);
  const [form, setForm] = useState(toForm(template()));
  const [selectedId, setSelectedId] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toDelete, setToDelete] = useState(null);

  const load = useCallback(async () => {
    const list = await listClusters();
    setClusters(list);
  }, []);
  useEffect(() => { load(); }, [load]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const selectCluster = (c) => {
    setSelectedId(c.id);
    setForm(toForm(c));
    setResult(null);
  };
  const newCluster = () => {
    setSelectedId(null);
    setForm(toForm(template()));
    setResult(null);
  };

  const setNode = (idx, key, val) =>
    setForm((f) => {
      const nodes = [...f.nodes];
      nodes[idx] = { ...nodes[idx], [key]: val };
      return { ...f, nodes };
    });
  const addNode = () =>
    setForm((f) => ({ ...f, nodes: [...f.nodes, { hostname: "", instance_type: "t3.medium", root_volume_size: 50 }] }));
  const removeNode = (idx) =>
    setForm((f) => ({ ...f, nodes: f.nodes.filter((_, i) => i !== idx) }));

  const save = async () => {
    setBusy(true);
    try {
      const payload = toPayload(form);
      if (selectedId) {
        await updateCluster(selectedId, payload);
        toast.success("Cluster saved");
      } else {
        const created = await createCluster(payload);
        setSelectedId(created.id);
        toast.success("Cluster created");
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    setBusy(true);
    try {
      const res = await previewCluster(toPayload(form));
      setResult(res);
      toast.success("Configuration generated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    await deleteCluster(toDelete.id);
    toast.success("Cluster deleted");
    if (selectedId === toDelete.id) newCluster();
    setToDelete(null);
    load();
  };

  return (
    <div>
      <PageHeader
        title="Kubernetes Provisioning"
        subtitle="Define a cluster spec → generate config JSON & Terraform"
        actions={
          <>
            <Button data-testid="new-cluster-button" variant="outline" onClick={newCluster}
              className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm gap-2">
              <Plus className="h-4 w-4" /> New
            </Button>
            <Button data-testid="save-cluster-button" onClick={save} disabled={busy}
              className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2">
              <Save className="h-4 w-4" /> {selectedId ? "Save" : "Create"}
            </Button>
          </>
        }
      />

      <div className="p-8 grid grid-cols-1 xl:grid-cols-[220px_1fr_1fr] gap-6">
        {/* saved clusters */}
        <div className="space-y-2">
          <h3 className="font-head font-semibold text-[11px] uppercase tracking-wider text-zinc-500 mb-2">
            Saved clusters
          </h3>
          {clusters.length === 0 && (
            <p className="text-xs text-zinc-600">None yet. Fill the form and Create.</p>
          )}
          {clusters.map((c) => (
            <div
              key={c.id}
              data-testid={`cluster-item-${c.id}`}
              onClick={() => selectCluster(c)}
              className={`group flex items-center justify-between px-3 py-2 rounded-sm cursor-pointer border transition-colors duration-150 ${
                selectedId === c.id
                  ? "bg-orange-500/10 border-orange-500/40 text-orange-300"
                  : "bg-[#18181B] border-[#27272A] text-zinc-300 hover:bg-white/5"
              }`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <Boxes className="h-3.5 w-3.5 shrink-0" />
                <span className="text-xs font-mono truncate">{c.name}</span>
              </div>
              {isAdmin && (
                <button
                  data-testid={`delete-cluster-${c.id}`}
                  onClick={(e) => { e.stopPropagation(); setToDelete(c); }}
                  className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 transition-opacity"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>

        {/* form */}
        <div className="space-y-5">
          <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-4 space-y-3">
            <h3 className="font-head font-semibold text-xs uppercase tracking-wider text-orange-500/80">Cluster</h3>
            <Field label="Config Name">
              <Input data-testid="k8s-name" className={inputCls} value={form.name} onChange={set("name")} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="AWS Region">
                <Input data-testid="k8s-region" className={inputCls} value={form.aws_region} onChange={set("aws_region")} />
              </Field>
              <Field label="Key Name">
                <Input data-testid="k8s-key" className={inputCls} value={form.key_name} onChange={set("key_name")} />
              </Field>
              <Field label="VPC Tag (Name)">
                <Input data-testid="k8s-vpc" className={inputCls} value={form.vpc_tag} onChange={set("vpc_tag")} />
              </Field>
              <Field label="Subnet Tag (Name)">
                <Input data-testid="k8s-subnet" className={inputCls} value={form.subnet_tag} onChange={set("subnet_tag")} />
              </Field>
              <Field label="Private Zone Name">
                <Input data-testid="k8s-zone" className={inputCls} value={form.private_zone_name} onChange={set("private_zone_name")} />
              </Field>
              <Field label="AMI ID (for Terraform)">
                <Input data-testid="k8s-ami" className={inputCls} value={form.ami_id} onChange={set("ami_id")} placeholder="ami-xxxx" />
              </Field>
            </div>
          </div>

          <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-4 space-y-3">
            <h3 className="font-head font-semibold text-xs uppercase tracking-wider text-orange-500/80">Tags (key=value per line)</h3>
            <Field label="Security Group Tags">
              <Textarea data-testid="k8s-sg-tags" className={`${inputCls} min-h-[70px]`} value={form.sg_tags} onChange={set("sg_tags")} />
            </Field>
            <Field label="Instance Tags">
              <Textarea data-testid="k8s-inst-tags" className={`${inputCls} min-h-[120px]`} value={form.inst_tags} onChange={set("inst_tags")} />
            </Field>
            <Field label="Volume Tags">
              <Textarea data-testid="k8s-vol-tags" className={`${inputCls} min-h-[120px]`} value={form.vol_tags} onChange={set("vol_tags")} />
            </Field>
          </div>

          <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-head font-semibold text-xs uppercase tracking-wider text-orange-500/80">
                Nodes ({form.nodes.length})
              </h3>
              <button data-testid="add-node-button" onClick={addNode} className="text-[11px] text-orange-500 hover:underline flex items-center gap-1">
                <Plus className="h-3 w-3" /> Add node
              </button>
            </div>
            <div className="grid grid-cols-[1fr_1fr_90px_28px] gap-2 text-[10px] uppercase tracking-wider text-zinc-600 px-1">
              <span>Hostname</span><span>Instance Type</span><span>Root GB</span><span />
            </div>
            {form.nodes.map((n, i) => (
              <div key={i} className="grid grid-cols-[1fr_1fr_90px_28px] gap-2 items-center">
                <Input data-testid={`node-hostname-${i}`} className={inputCls} value={n.hostname} onChange={(e) => setNode(i, "hostname", e.target.value)} placeholder="controller0" />
                <Input data-testid={`node-type-${i}`} className={inputCls} value={n.instance_type} onChange={(e) => setNode(i, "instance_type", e.target.value)} />
                <Input data-testid={`node-size-${i}`} className={inputCls} value={n.root_volume_size} onChange={(e) => setNode(i, "root_volume_size", e.target.value)} />
                <button onClick={() => removeNode(i)} className="text-zinc-600 hover:text-red-400 flex justify-center">
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>

          <Button data-testid="k8s-generate-button" onClick={generate} disabled={busy}
            className="w-full bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2 h-11">
            <Zap className="h-4 w-4" /> {busy ? "Generating…" : "Generate JSON & Terraform"}
          </Button>
        </div>

        {/* output */}
        <div>
          {result ? (
            <Tabs defaultValue="json">
              <TabsList className="bg-[#18181B] border border-[#27272A] rounded-sm">
                <TabsTrigger value="json" data-testid="k8s-tab-json" className="data-[state=active]:bg-orange-500 data-[state=active]:text-white rounded-sm">
                  cluster.json
                </TabsTrigger>
                <TabsTrigger value="hcl" data-testid="k8s-tab-hcl" className="data-[state=active]:bg-orange-500 data-[state=active]:text-white rounded-sm">
                  main.tf (HCL)
                </TabsTrigger>
              </TabsList>
              <TabsContent value="json" className="mt-3">
                <CodeBlock code={result.config_json || ""} language="json" filename="cluster.json" />
              </TabsContent>
              <TabsContent value="hcl" className="mt-3">
                <CodeBlock code={result.hcl || ""} language="hcl" filename="main.tf" />
              </TabsContent>
            </Tabs>
          ) : (
            <div className="h-full min-h-[400px] flex flex-col items-center justify-center border border-dashed border-white/10 rounded-sm">
              <Server className="h-10 w-10 text-zinc-700 mb-3" strokeWidth={1.25} />
              <p className="text-sm text-zinc-500">Generate to preview cluster JSON & Terraform</p>
              <p className="text-xs text-zinc-600 mt-1">Nodes, tags, VPC/subnet & Route53 records</p>
            </div>
          )}
        </div>
      </div>

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent className="bg-[#18181B] border-[#27272A] text-white">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-head">Delete cluster config?</AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              <span className="font-mono text-white">{toDelete?.name}</span> will be permanently removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-delete-cluster" onClick={confirmDelete} className="bg-red-500 hover:bg-red-600 text-white rounded-sm">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
