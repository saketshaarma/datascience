import { useEffect, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { createInstance, updateInstance } from "@/lib/api";
import { toast } from "sonner";

const empty = {
  instance_name: "", host: "", port: "", instance_role: "",
  ec2_instance_type: "", ami_id: "", region: "us-east-1",
  availability_zone: "", vpc_id: "", subnet_id: "", key_name: "",
  dns_records: "", srv_records: "", notes: "",
};

const Field = ({ label, children }) => (
  <div className="space-y-1.5">
    <Label className="text-xs text-zinc-400">{label}</Label>
    {children}
  </div>
);

const inputCls =
  "bg-[#09090B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2";

export const InstanceForm = ({ open, onOpenChange, instance, onSaved }) => {
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (instance) {
      setForm({
        ...empty,
        ...instance,
        port: instance.port ?? "",
        dns_records: (instance.dns_records || []).join("\n"),
        srv_records: (instance.srv_records || []).join("\n"),
      });
    } else {
      setForm(empty);
    }
  }, [instance, open]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async () => {
    if (!form.host && !form.instance_name) {
      toast.error("Provide at least an instance name or host");
      return;
    }
    setSaving(true);
    const payload = {
      ...form,
      port: form.port ? parseInt(form.port, 10) : null,
      dns_records: form.dns_records.split("\n").map((s) => s.trim()).filter(Boolean),
      srv_records: form.srv_records.split("\n").map((s) => s.trim()).filter(Boolean),
    };
    try {
      if (instance) {
        await updateInstance(instance.id, payload);
        toast.success("Instance updated");
      } else {
        await createInstance(payload);
        toast.success("Instance created");
      }
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error("Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#18181B] border-[#27272A] text-white max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-head">
            {instance ? "Edit Instance" : "Add Instance"}
          </DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-4 py-2">
          <Field label="Instance Name">
            <Input data-testid="form-instance-name" className={inputCls} value={form.instance_name} onChange={set("instance_name")} placeholder="JaLsi" />
          </Field>
          <Field label="Instance Role">
            <Input data-testid="form-instance-role" className={inputCls} value={form.instance_role} onChange={set("instance_role")} placeholder="slave / master" />
          </Field>
          <Field label="Host (IP)">
            <Input data-testid="form-host" className={inputCls} value={form.host} onChange={set("host")} placeholder="172.10.112.169" />
          </Field>
          <Field label="Port">
            <Input data-testid="form-port" className={inputCls} value={form.port} onChange={set("port")} placeholder="3306" />
          </Field>
          <Field label="EC2 Instance Type">
            <Input data-testid="form-ec2-type" className={inputCls} value={form.ec2_instance_type} onChange={set("ec2_instance_type")} placeholder="t3.medium" />
          </Field>
          <Field label="AMI ID">
            <Input data-testid="form-ami" className={inputCls} value={form.ami_id} onChange={set("ami_id")} placeholder="ami-0c55b159..." />
          </Field>
          <Field label="Region">
            <Input className={inputCls} value={form.region} onChange={set("region")} placeholder="us-east-1" />
          </Field>
          <Field label="Availability Zone">
            <Input className={inputCls} value={form.availability_zone} onChange={set("availability_zone")} placeholder="us-east-1a" />
          </Field>
          <Field label="VPC ID">
            <Input className={inputCls} value={form.vpc_id} onChange={set("vpc_id")} placeholder="vpc-xxxx" />
          </Field>
          <Field label="Subnet ID">
            <Input className={inputCls} value={form.subnet_id} onChange={set("subnet_id")} placeholder="subnet-xxxx" />
          </Field>
          <Field label="Key Name">
            <Input className={inputCls} value={form.key_name} onChange={set("key_name")} placeholder="prod-key" />
          </Field>
          <div />
          <Field label="DNS Records (one per line)">
            <Textarea data-testid="form-dns" className={`${inputCls} min-h-[100px]`} value={form.dns_records} onChange={set("dns_records")} placeholder="db.analytics.asdex.com" />
          </Field>
          <Field label="SRV Records (one per line)">
            <Textarea data-testid="form-srv" className={`${inputCls} min-h-[100px]`} value={form.srv_records} onChange={set("srv_records")} placeholder="srv.analytics.asdex.com" />
          </Field>
          <div className="col-span-2">
            <Field label="Notes">
              <Textarea className={inputCls} value={form.notes} onChange={set("notes")} />
            </Field>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">
            Cancel
          </Button>
          <Button data-testid="form-save-button" onClick={submit} disabled={saving} className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm">
            {saving ? "Saving..." : "Save Instance"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
