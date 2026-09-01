import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus, Save, Zap, Trash2, Server, Boxes, X, Settings2, Tags, Network,
  ClipboardCheck, ChevronLeft, ChevronRight, Check, Cpu, HardDrive, Database, ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
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

const objToArr = (o) => Object.entries(o || {}).map(([key, value]) => ({ key, value }));
const arrToObj = (a) => {
  const o = {};
  (a || []).forEach(({ key, value }) => { if ((key || "").trim()) o[key.trim()] = value; });
  return o;
};

const STEPS = [
  { key: "basics", label: "Cluster", icon: Settings2 },
  { key: "tags", label: "Tags", icon: Tags },
  { key: "nodes", label: "Nodes", icon: Network },
  { key: "review", label: "Review", icon: ClipboardCheck },
];

const template = () => ({
  name: "analytics-cluster",
  aws_region: "ap-south-2",
  vpc_tag: "Pakri-analytics-db-vpc",
  subnet_tag: "Pakri-analytics-db-pvt",
  key_name: "HYD",
  private_zone_name: "ieil.net",
  ami_id: "",
  sgTags: objToArr({ Environment: "Backup", Role: "SRE" }),
  instTags: objToArr({
    Environment: "prod", GroupName: "NM-PakriAnalytics", Business: "BKP-DataScience-Pakri",
    BU: "DataScience", ManagedBy: "Terraform", Owner: "SRE", Application: "Kubernates-node", DR: "Yes",
  }),
  volTags: objToArr({
    Environment: "prod", GroupName: "NM-PakriAnalytics", Business: "BKP-DataScience-Pakri",
    BU: "DataScience", ManagedBy: "Terraform", Owner: "SRE", Application: "Kubernates-node", DR: "Yes",
  }),
  nodes: [
    { hostname: "controller0", instance_type: "t3.medium", root_volume_size: 50 },
    { hostname: "controller1", instance_type: "t3.medium", root_volume_size: 50 },
    { hostname: "controller2", instance_type: "t3.medium", root_volume_size: 50 },
    { hostname: "etcd3", instance_type: "t3.medium", root_volume_size: 50 },
    { hostname: "etcd4", instance_type: "t3.medium", root_volume_size: 50 },
  ],
});

const toForm = (c) => ({
  name: c.name, aws_region: c.aws_region, vpc_tag: c.vpc_tag, subnet_tag: c.subnet_tag,
  key_name: c.key_name, private_zone_name: c.private_zone_name, ami_id: c.ami_id || "",
  sgTags: objToArr(c.security_group_tags), instTags: objToArr(c.instance_tags),
  volTags: objToArr(c.volume_tags),
  nodes: (c.nodes || []).map((n) => ({ ...n })),
});

const toPayload = (f) => ({
  name: f.name, aws_region: f.aws_region, vpc_tag: f.vpc_tag, subnet_tag: f.subnet_tag,
  key_name: f.key_name, private_zone_name: f.private_zone_name, ami_id: f.ami_id || "",
  security_group_tags: arrToObj(f.sgTags), instance_tags: arrToObj(f.instTags),
  volume_tags: arrToObj(f.volTags),
  nodes: (f.nodes || []).map((n) => ({
    hostname: n.hostname, instance_type: n.instance_type,
    root_volume_size: parseInt(n.root_volume_size, 10) || 0,
  })),
  extra: {},
});

const Field = ({ label, children, hint }) => (
  <div className="space-y-1.5">
    <Label className="text-xs text-zinc-400">{label}</Label>
    {children}
    {hint && <p className="text-[10px] text-zinc-600 font-mono">{hint}</p>}
  </div>
);

const KVEditor = ({ items, onChange, testid }) => {
  const set = (i, k, v) => {
    const next = [...items];
    next[i] = { ...next[i], [k]: v };
    onChange(next);
  };
  const add = () => onChange([...items, { key: "", value: "" }]);
  const remove = (i) => onChange(items.filter((_, idx) => idx !== i));
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_28px] gap-2 items-center">
          <Input data-testid={`${testid}-key-${i}`} className={inputCls} value={it.key} onChange={(e) => set(i, "key", e.target.value)} placeholder="Key" />
          <Input data-testid={`${testid}-val-${i}`} className={inputCls} value={it.value} onChange={(e) => set(i, "value", e.target.value)} placeholder="Value" />
          <button onClick={() => remove(i)} className="text-zinc-600 hover:text-red-400 flex justify-center transition-colors duration-150">
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
      <button data-testid={`${testid}-add`} onClick={add} className="text-[11px] text-orange-500 hover:underline flex items-center gap-1 mt-1">
        <Plus className="h-3 w-3" /> Add tag
      </button>
    </div>
  );
};

export default function Kubernetes() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [clusters, setClusters] = useState([]);
  const [form, setForm] = useState(template());
  const [selectedId, setSelectedId] = useState("new");
  const [step, setStep] = useState(0);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toDelete, setToDelete] = useState(null);

  const load = useCallback(async () => setClusters(await listClusters()), []);
  useEffect(() => { load(); }, [load]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const loadCluster = (id) => {
    setResult(null); setStep(0);
    if (id === "new") { setSelectedId("new"); setForm(template()); return; }
    const c = clusters.find((x) => x.id === id);
    if (c) { setSelectedId(id); setForm(toForm(c)); }
  };

  // node helpers
  const setNode = (idx, key, val) => setForm((f) => {
    const nodes = [...f.nodes]; nodes[idx] = { ...nodes[idx], [key]: val }; return { ...f, nodes };
  });
  const addNode = (preset) => setForm((f) => {
    const base = { controller: "controller", etcd: "etcd", worker: "worker" }[preset] || "node";
    const n = f.nodes.filter((x) => x.hostname.startsWith(base)).length;
    return { ...f, nodes: [...f.nodes, { hostname: `${base}${n}`, instance_type: "t3.medium", root_volume_size: 50 }] };
  });
  const removeNode = (idx) => setForm((f) => ({ ...f, nodes: f.nodes.filter((_, i) => i !== idx) }));

  const save = async () => {
    setBusy(true);
    try {
      const payload = toPayload(form);
      if (selectedId !== "new") {
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
    } finally { setBusy(false); }
  };

  const generate = async () => {
    setBusy(true);
    try {
      const res = await previewCluster(toPayload(form));
      setResult(res);
      toast.success("Configuration generated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally { setBusy(false); }
  };

  const confirmDelete = async () => {
    await deleteCluster(toDelete.id);
    toast.success("Cluster deleted");
    if (selectedId === toDelete.id) loadCluster("new");
    setToDelete(null); load();
  };

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));
  const progress = ((step + 1) / STEPS.length) * 100;

  const fileList = result
    ? [
        { name: "cluster.json", content: result.config_json || "" },
        ...Object.entries(result.files || {}).map(([name, content]) => ({ name, content })),
      ]
    : [];

  const downloadAll = () => {
    fileList.forEach((f, i) => {
      setTimeout(() => {
        const blob = new Blob([f.content], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = f.name;
        a.click();
        URL.revokeObjectURL(url);
      }, i * 250);
    });
    toast.success(`Downloading ${fileList.length} files`);
  };

  return (
    <div>
      <PageHeader
        title="Kubernetes Provisioning"
        subtitle="Guided wizard → cluster config JSON & Terraform"
        actions={
          <div className="flex items-center gap-2">
            <Select value={selectedId} onValueChange={loadCluster}>
              <SelectTrigger data-testid="cluster-select" className="w-52 bg-[#18181B] border-[#27272A] text-white text-sm rounded-sm">
                <SelectValue placeholder="Load saved…" />
              </SelectTrigger>
              <SelectContent className="bg-[#18181B] border-[#27272A] text-white">
                <SelectItem value="new">+ New cluster</SelectItem>
                {clusters.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
            {selectedId !== "new" && isAdmin && (
              <Button data-testid="delete-cluster-button" variant="outline" size="icon"
                onClick={() => setToDelete(clusters.find((c) => c.id === selectedId))}
                className="border-white/20 bg-transparent text-zinc-400 hover:text-red-400 hover:bg-red-500/10 rounded-sm">
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
            <Button data-testid="save-cluster-button" onClick={save} disabled={busy}
              className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2">
              <Save className="h-4 w-4" /> {selectedId !== "new" ? "Save" : "Create"}
            </Button>
          </div>
        }
      />

      <div className="p-8 max-w-6xl">
        {/* Stepper */}
        <div className="mb-8">
          <div className="flex items-center">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              const done = i < step;
              const active = i === step;
              return (
                <div key={s.key} className="flex items-center flex-1 last:flex-none">
                  <button
                    data-testid={`step-${s.key}`}
                    onClick={() => setStep(i)}
                    className="flex items-center gap-3 group"
                  >
                    <span className={`h-10 w-10 rounded-sm flex items-center justify-center border transition-colors duration-200 ${
                      active ? "bg-orange-500 border-orange-500 text-black"
                      : done ? "bg-orange-500/15 border-orange-500/50 text-orange-400"
                      : "bg-[#18181B] border-[#27272A] text-zinc-500"
                    }`}>
                      {done ? <Check className="h-5 w-5" /> : <Icon className="h-5 w-5" strokeWidth={1.75} />}
                    </span>
                    <div className="text-left hidden sm:block">
                      <div className={`text-[10px] font-mono uppercase tracking-wider ${active || done ? "text-orange-400" : "text-zinc-600"}`}>Step {i + 1}</div>
                      <div className={`text-sm font-head font-semibold ${active ? "text-white" : "text-zinc-400"}`}>{s.label}</div>
                    </div>
                  </button>
                  {i < STEPS.length - 1 && (
                    <div className="flex-1 h-px mx-4 bg-[#27272A] relative overflow-hidden">
                      <div className="absolute inset-0 bg-orange-500 transition-transform duration-300 origin-left"
                        style={{ transform: `scaleX(${i < step ? 1 : 0})` }} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-5 h-1 bg-[#18181B] rounded-full overflow-hidden">
            <div className="h-full bg-orange-500 transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
        </div>

        {/* Step content */}
        <div className="bg-[#18181B] border border-[#27272A] rounded-sm p-6 min-h-[360px]">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -16 }}
              transition={{ duration: 0.2 }}
            >
              {step === 0 && (
                <div className="space-y-5">
                  <StepTitle icon={Settings2} title="Cluster basics" desc="Where and how the cluster is deployed" />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <Field label="Config Name">
                      <Input data-testid="k8s-name" className={inputCls} value={form.name} onChange={set("name")} />
                    </Field>
                    <Field label="AWS Region">
                      <Input data-testid="k8s-region" className={inputCls} value={form.aws_region} onChange={set("aws_region")} />
                    </Field>
                    <Field label="Key Name">
                      <Input data-testid="k8s-key" className={inputCls} value={form.key_name} onChange={set("key_name")} />
                    </Field>
                    <Field label="AMI ID (for Terraform)" hint="Leave blank to set at apply time">
                      <Input data-testid="k8s-ami" className={inputCls} value={form.ami_id} onChange={set("ami_id")} placeholder="ami-xxxx" />
                    </Field>
                    <Field label="VPC Tag (Name)">
                      <Input data-testid="k8s-vpc" className={inputCls} value={form.vpc_tag} onChange={set("vpc_tag")} />
                    </Field>
                    <Field label="Subnet Tag (Name)">
                      <Input data-testid="k8s-subnet" className={inputCls} value={form.subnet_tag} onChange={set("subnet_tag")} />
                    </Field>
                    <Field label="Private Zone Name" hint="Route53 private hosted zone">
                      <Input data-testid="k8s-zone" className={inputCls} value={form.private_zone_name} onChange={set("private_zone_name")} />
                    </Field>
                  </div>
                </div>
              )}

              {step === 1 && (
                <div className="space-y-6">
                  <StepTitle icon={Tags} title="Tags" desc="Tags applied to instances, volumes and the security group" />
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <TagCard icon={ShieldCheck} title="Security Group Tags">
                      <KVEditor items={form.sgTags} onChange={(v) => setForm((f) => ({ ...f, sgTags: v }))} testid="k8s-sg" />
                    </TagCard>
                    <TagCard icon={Server} title="Instance Tags">
                      <KVEditor items={form.instTags} onChange={(v) => setForm((f) => ({ ...f, instTags: v }))} testid="k8s-inst" />
                    </TagCard>
                    <TagCard icon={HardDrive} title="Volume Tags">
                      <KVEditor items={form.volTags} onChange={(v) => setForm((f) => ({ ...f, volTags: v }))} testid="k8s-vol" />
                    </TagCard>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-5">
                  <StepTitle icon={Network} title="Nodes" desc="Each node becomes an EC2 instance with a private DNS record" />
                  <div className="flex flex-wrap gap-2">
                    <PresetBtn onClick={() => addNode("controller")} label="Add controller" />
                    <PresetBtn onClick={() => addNode("etcd")} label="Add etcd" />
                    <PresetBtn onClick={() => addNode("worker")} label="Add worker" />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                    {form.nodes.map((n, i) => (
                      <div key={i} data-testid={`node-card-${i}`} className="bg-[#09090B] border border-[#27272A] rounded-sm p-3 space-y-2.5 relative group">
                        <button onClick={() => removeNode(i)} className="absolute top-2 right-2 text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">
                          <X className="h-4 w-4" />
                        </button>
                        <div className="flex items-center gap-2 text-orange-500">
                          <Boxes className="h-4 w-4" />
                          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">node{i + 1}</span>
                        </div>
                        <Field label="Hostname">
                          <Input data-testid={`node-hostname-${i}`} className={inputCls} value={n.hostname} onChange={(e) => setNode(i, "hostname", e.target.value)} />
                        </Field>
                        <div className="grid grid-cols-2 gap-2">
                          <Field label="Type">
                            <Input data-testid={`node-type-${i}`} className={inputCls} value={n.instance_type} onChange={(e) => setNode(i, "instance_type", e.target.value)} />
                          </Field>
                          <Field label="Root GB">
                            <Input data-testid={`node-size-${i}`} className={inputCls} value={n.root_volume_size} onChange={(e) => setNode(i, "root_volume_size", e.target.value)} />
                          </Field>
                        </div>
                      </div>
                    ))}
                    <button data-testid="add-node-button" onClick={() => addNode("node")}
                      className="border border-dashed border-white/15 rounded-sm flex flex-col items-center justify-center gap-2 text-zinc-500 hover:text-orange-400 hover:border-orange-500/40 transition-colors duration-150 min-h-[150px]">
                      <Plus className="h-6 w-6" />
                      <span className="text-xs">Add node</span>
                    </button>
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="space-y-5">
                  <StepTitle icon={ClipboardCheck} title="Review & generate" desc="Confirm the spec, then generate JSON & Terraform" />
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <Summary icon={Settings2} label="Region" value={form.aws_region} />
                    <Summary icon={Network} label="VPC" value={form.vpc_tag} />
                    <Summary icon={Network} label="Subnet" value={form.subnet_tag} />
                    <Summary icon={Database} label="Zone" value={form.private_zone_name} />
                    <Summary icon={Boxes} label="Nodes" value={String(form.nodes.length)} />
                    <Summary icon={ShieldCheck} label="SG Tags" value={String(form.sgTags.filter(t => t.key).length)} />
                    <Summary icon={Server} label="Inst Tags" value={String(form.instTags.filter(t => t.key).length)} />
                    <Summary icon={HardDrive} label="Vol Tags" value={String(form.volTags.filter(t => t.key).length)} />
                  </div>

                  <Button data-testid="k8s-generate-button" onClick={generate} disabled={busy}
                    className="w-full bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2 h-11">
                    <Zap className="h-4 w-4" /> {busy ? "Generating…" : "Generate JSON & Terraform"}
                  </Button>

                  {result && (
                    <div className="mt-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500 font-mono">
                          Modular Terraform project · {Object.keys(result.files || {}).length + 1} files
                        </span>
                        <Button data-testid="k8s-download-all" onClick={downloadAll} variant="outline"
                          className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm gap-2 h-8 text-xs">
                          <Save className="h-3.5 w-3.5" /> Download all
                        </Button>
                      </div>
                      <Tabs defaultValue="cluster.json">
                        <TabsList className="bg-[#09090B] border border-[#27272A] rounded-sm flex-wrap h-auto">
                          {fileList.map((f) => (
                            <TabsTrigger key={f.name} value={f.name} data-testid={`k8s-tab-${f.name}`}
                              className="data-[state=active]:bg-orange-500 data-[state=active]:text-white rounded-sm text-xs">
                              {f.name}
                            </TabsTrigger>
                          ))}
                        </TabsList>
                        {fileList.map((f) => (
                          <TabsContent key={f.name} value={f.name} className="mt-3">
                            <CodeBlock code={f.content} language={f.name.endsWith(".json") ? "json" : "hcl"} filename={f.name} />
                          </TabsContent>
                        ))}
                      </Tabs>
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Wizard nav */}
        <div className="flex items-center justify-between mt-5">
          <Button data-testid="wizard-back" variant="outline" onClick={back} disabled={step === 0}
            className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm gap-2 disabled:opacity-40">
            <ChevronLeft className="h-4 w-4" /> Back
          </Button>
          {step < STEPS.length - 1 ? (
            <Button data-testid="wizard-next" onClick={next}
              className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2">
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          ) : (
            <span className="text-xs text-zinc-600 font-mono">Step {step + 1} of {STEPS.length}</span>
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

const StepTitle = ({ icon: Icon, title, desc }) => (
  <div className="flex items-start gap-3 pb-4 mb-2 border-b border-[#27272A]">
    <div className="h-9 w-9 rounded-sm bg-orange-500/10 flex items-center justify-center shrink-0">
      <Icon className="h-5 w-5 text-orange-500" strokeWidth={1.75} />
    </div>
    <div>
      <h3 className="font-head font-semibold text-white">{title}</h3>
      <p className="text-xs text-zinc-500">{desc}</p>
    </div>
  </div>
);

const TagCard = ({ icon: Icon, title, children }) => (
  <div className="bg-[#09090B] border border-[#27272A] rounded-sm p-4">
    <div className="flex items-center gap-2 mb-3">
      <Icon className="h-4 w-4 text-orange-500" strokeWidth={1.75} />
      <span className="font-head font-semibold text-xs uppercase tracking-wider text-zinc-300">{title}</span>
    </div>
    {children}
  </div>
);

const PresetBtn = ({ onClick, label }) => (
  <button onClick={onClick} className="px-3 py-1.5 rounded-sm border border-[#27272A] bg-[#09090B] text-xs text-zinc-300 hover:border-orange-500/40 hover:text-orange-400 transition-colors duration-150 flex items-center gap-1.5">
    <Plus className="h-3 w-3" /> {label}
  </button>
);

const Summary = ({ icon: Icon, label, value }) => (
  <div className="bg-[#09090B] border border-[#27272A] rounded-sm p-3">
    <div className="flex items-center gap-2 text-zinc-500 mb-1.5">
      <Icon className="h-3.5 w-3.5" />
      <span className="text-[10px] uppercase tracking-wider font-mono">{label}</span>
    </div>
    <div className="font-mono text-sm text-white truncate" title={value}>{value || "—"}</div>
  </div>
);
