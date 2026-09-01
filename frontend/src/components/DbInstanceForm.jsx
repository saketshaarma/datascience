import { useEffect, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Plus, X } from "lucide-react";
import { createDbInstance, updateDbInstance } from "@/lib/api";
import { toast } from "sonner";

const ENVS = ["DEV", "QA", "UAT", "DR", "PROD"];
const STATUSES = ["Running", "Stopped", "Terminated"];

const inputCls =
  "bg-[#09090B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2";

const empty = (serviceId) => ({
  service_id: serviceId || "", instance_name: "", host: "", port: "",
  instance_type: "", aws_instance_id: "", all_dns: "", srv_record: "",
  aws_region: "", environment: "DEV", status: "Running", metadata: [],
});

const Field = ({ label, children }) => (
  <div className="space-y-1.5">
    <Label className="text-xs text-zinc-400">{label}</Label>
    {children}
  </div>
);

export const DbInstanceForm = ({ open, onOpenChange, instance, services, defaultServiceId, onSaved }) => {
  const [form, setForm] = useState(empty(defaultServiceId));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (instance) {
      setForm({ ...empty(), ...instance, port: instance.port ?? "", metadata: instance.metadata || [] });
    } else {
      setForm(empty(defaultServiceId));
    }
  }, [instance, open, defaultServiceId]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setMeta = (i, key, val) => setForm((f) => {
    const metadata = [...f.metadata];
    metadata[i] = { ...metadata[i], [key]: val };
    return { ...f, metadata };
  });
  const addMeta = () => setForm((f) => ({ ...f, metadata: [...f.metadata, { attribute_key: "", attribute_value: "" }] }));
  const removeMeta = (i) => setForm((f) => ({ ...f, metadata: f.metadata.filter((_, idx) => idx !== i) }));

  const submit = async () => {
    if (!form.service_id) { toast.error("Select a service"); return; }
    if (!form.instance_name.trim()) { toast.error("Instance name required"); return; }
    setSaving(true);
    const payload = {
      ...form,
      port: form.port ? parseInt(form.port, 10) : null,
      metadata: form.metadata.filter((m) => (m.attribute_key || "").trim()),
    };
    try {
      if (instance) {
        await updateDbInstance(instance.id, payload);
        toast.success("Instance updated");
      } else {
        await createDbInstance(payload);
        toast.success("Instance created");
      }
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#18181B] border-[#27272A] text-white max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-head">{instance ? "Edit DB Instance" : "Add DB Instance"}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-4 py-2">
          <Field label="Service">
            <Select value={form.service_id} onValueChange={(v) => setForm((f) => ({ ...f, service_id: v }))}>
              <SelectTrigger data-testid="db-form-service" className={inputCls}><SelectValue placeholder="Select service" /></SelectTrigger>
              <SelectContent className="bg-[#18181B] border-[#27272A] text-white">
                {services.map((s) => <SelectItem key={s.id} value={s.id}>{s.service_name}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Instance Name">
            <Input data-testid="db-form-name" className={inputCls} value={form.instance_name} onChange={set("instance_name")} placeholder="prod-mysql-1" />
          </Field>
          <Field label="Host">
            <Input data-testid="db-form-host" className={inputCls} value={form.host} onChange={set("host")} placeholder="10.0.0.5" />
          </Field>
          <Field label="Port">
            <Input data-testid="db-form-port" className={inputCls} value={form.port} onChange={set("port")} placeholder="3306" />
          </Field>
          <Field label="Instance Type">
            <Input data-testid="db-form-type" className={inputCls} value={form.instance_type} onChange={set("instance_type")} placeholder="db.r5.large" />
          </Field>
          <Field label="AWS Instance ID (unique)">
            <Input data-testid="db-form-awsid" className={inputCls} value={form.aws_instance_id} onChange={set("aws_instance_id")} placeholder="i-0abc123" />
          </Field>
          <Field label="All DNS">
            <Input data-testid="db-form-dns" className={inputCls} value={form.all_dns} onChange={set("all_dns")} placeholder="db.example.com" />
          </Field>
          <Field label="SRV Record">
            <Input data-testid="db-form-srv" className={inputCls} value={form.srv_record} onChange={set("srv_record")} />
          </Field>
          <Field label="AWS Region">
            <Input data-testid="db-form-region" className={inputCls} value={form.aws_region} onChange={set("aws_region")} placeholder="ap-south-1" />
          </Field>
          <Field label="Environment">
            <Select value={form.environment} onValueChange={(v) => setForm((f) => ({ ...f, environment: v }))}>
              <SelectTrigger data-testid="db-form-env" className={inputCls}><SelectValue /></SelectTrigger>
              <SelectContent className="bg-[#18181B] border-[#27272A] text-white">
                {ENVS.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Status">
            <Select value={form.status} onValueChange={(v) => setForm((f) => ({ ...f, status: v }))}>
              <SelectTrigger data-testid="db-form-status" className={inputCls}><SelectValue /></SelectTrigger>
              <SelectContent className="bg-[#18181B] border-[#27272A] text-white">
                {STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>

          <div className="col-span-2 pt-2 border-t border-[#27272A]">
            <div className="flex items-center justify-between mb-2">
              <span className="font-head font-semibold text-[11px] uppercase tracking-wider text-orange-500/80">Metadata (attributes)</span>
              <button data-testid="db-add-meta" onClick={addMeta} className="text-[11px] text-orange-500 hover:underline flex items-center gap-1">
                <Plus className="h-3 w-3" /> Add attribute
              </button>
            </div>
            {form.metadata.length === 0 && <p className="text-xs text-zinc-600">No attributes.</p>}
            <div className="space-y-2">
              {form.metadata.map((m, i) => (
                <div key={i} className="grid grid-cols-[1fr_1fr_28px] gap-2 items-center">
                  <Input data-testid={`db-meta-key-${i}`} className={inputCls} value={m.attribute_key} onChange={(e) => setMeta(i, "attribute_key", e.target.value)} placeholder="key" />
                  <Input data-testid={`db-meta-val-${i}`} className={inputCls} value={m.attribute_value} onChange={(e) => setMeta(i, "attribute_value", e.target.value)} placeholder="value" />
                  <button onClick={() => removeMeta(i)} className="text-zinc-600 hover:text-red-400 flex justify-center"><X className="h-4 w-4" /></button>
                </div>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</Button>
          <Button data-testid="db-form-save" onClick={submit} disabled={saving} className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm">
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
