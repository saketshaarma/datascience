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
  instance_name: "", environment: "", instance_role: "", host: "", port: "",
  region: "us-east-1", ec2_instance_id: "", ec2_instance_type: "", ami_id: "",
  vpc_id: "", subnet_id: "", availability_zone: "", private_ip: "", public_ip: "",
  iam_instance_profile: "", key_name: "",
  security_groups: "", ebs_volumes: "", dns_records: "", srv_records: "",
  tags: "", custom_metadata: "", notes: "",
};

const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const linesToObj = (s) => {
  const o = {};
  lines(s).forEach((l) => {
    const i = l.indexOf("=");
    if (i > 0) o[l.slice(0, i).trim()] = l.slice(i + 1).trim();
  });
  return o;
};
const objToLines = (o) => Object.entries(o || {}).map(([k, v]) => `${k}=${v}`).join("\n");
const parseEbs = (s) =>
  lines(s).map((l) => {
    const [device_name = "", size = "", volume_type = "gp3"] = l.split(":");
    return { device_name: device_name.trim(), size_gb: size ? parseInt(size, 10) : null, volume_type: volume_type.trim() || "gp3" };
  });
const ebsToLines = (arr) =>
  (arr || []).map((v) => `${v.device_name}:${v.size_gb ?? ""}:${v.volume_type || "gp3"}`).join("\n");

const inputCls =
  "bg-[#09090B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2";

const Field = ({ label, hint, children, full }) => (
  <div className={`space-y-1.5 ${full ? "col-span-2" : ""}`}>
    <Label className="text-xs text-zinc-400">{label}</Label>
    {children}
    {hint && <p className="text-[10px] text-zinc-600 font-mono">{hint}</p>}
  </div>
);

const Section = ({ title }) => (
  <div className="col-span-2 pt-2 pb-1 mt-1 border-b border-[#27272A]">
    <span className="font-head font-semibold text-[11px] uppercase tracking-wider text-orange-500/80">{title}</span>
  </div>
);

export const InstanceForm = ({ open, onOpenChange, instance, onSaved }) => {
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (instance) {
      setForm({
        ...empty,
        ...instance,
        port: instance.port ?? "",
        security_groups: (instance.security_groups || []).join("\n"),
        ebs_volumes: ebsToLines(instance.ebs_volumes),
        dns_records: (instance.dns_records || []).join("\n"),
        srv_records: (instance.srv_records || []).join("\n"),
        tags: objToLines(instance.tags),
        custom_metadata: objToLines(instance.custom_metadata),
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
      security_groups: lines(form.security_groups),
      ebs_volumes: parseEbs(form.ebs_volumes),
      dns_records: lines(form.dns_records),
      srv_records: lines(form.srv_records),
      tags: linesToObj(form.tags),
      custom_metadata: linesToObj(form.custom_metadata),
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
      <DialogContent className="bg-[#18181B] border-[#27272A] text-white max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-head">{instance ? "Edit Instance" : "Add Instance"}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-4 py-2">
          <Section title="Identity" />
          <Field label="Instance Name">
            <Input data-testid="form-instance-name" className={inputCls} value={form.instance_name} onChange={set("instance_name")} placeholder="JaLsi" />
          </Field>
          <Field label="Environment">
            <Input data-testid="form-environment" className={inputCls} value={form.environment} onChange={set("environment")} placeholder="prod / staging / dev" />
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

          <Section title="EC2 & AMI" />
          <Field label="EC2 Instance ID">
            <Input data-testid="form-ec2-id" className={inputCls} value={form.ec2_instance_id} onChange={set("ec2_instance_id")} placeholder="i-0abc123..." />
          </Field>
          <Field label="EC2 Instance Type">
            <Input data-testid="form-ec2-type" className={inputCls} value={form.ec2_instance_type} onChange={set("ec2_instance_type")} placeholder="t3.medium" />
          </Field>
          <Field label="AMI ID">
            <Input data-testid="form-ami" className={inputCls} value={form.ami_id} onChange={set("ami_id")} placeholder="ami-0c55b159..." />
          </Field>
          <Field label="Key Name">
            <Input className={inputCls} value={form.key_name} onChange={set("key_name")} placeholder="prod-key" />
          </Field>

          <Section title="Networking" />
          <Field label="AWS Region">
            <Input data-testid="form-region" className={inputCls} value={form.region} onChange={set("region")} placeholder="us-east-1" />
          </Field>
          <Field label="Availability Zone">
            <Input data-testid="form-az" className={inputCls} value={form.availability_zone} onChange={set("availability_zone")} placeholder="us-east-1a" />
          </Field>
          <Field label="VPC ID">
            <Input data-testid="form-vpc" className={inputCls} value={form.vpc_id} onChange={set("vpc_id")} placeholder="vpc-xxxx" />
          </Field>
          <Field label="Subnet ID">
            <Input data-testid="form-subnet" className={inputCls} value={form.subnet_id} onChange={set("subnet_id")} placeholder="subnet-xxxx" />
          </Field>
          <Field label="Private IP">
            <Input data-testid="form-private-ip" className={inputCls} value={form.private_ip} onChange={set("private_ip")} placeholder="10.0.1.20" />
          </Field>
          <Field label="Public IP">
            <Input data-testid="form-public-ip" className={inputCls} value={form.public_ip} onChange={set("public_ip")} placeholder="52.1.2.3" />
          </Field>
          <Field label="IAM Instance Profile" full>
            <Input data-testid="form-iam" className={inputCls} value={form.iam_instance_profile} onChange={set("iam_instance_profile")} placeholder="ec2-app-role" />
          </Field>
          <Field label="Security Groups (one per line)" hint="sg-0abc / group name" full>
            <Textarea data-testid="form-sg" className={`${inputCls} min-h-[70px]`} value={form.security_groups} onChange={set("security_groups")} placeholder={"sg-0123456789\nsg-abcdef"} />
          </Field>

          <Section title="Storage" />
          <Field label="EBS Volumes (device:size_gb:type per line)" hint="e.g. /dev/sdf:100:gp3" full>
            <Textarea data-testid="form-ebs" className={`${inputCls} min-h-[70px]`} value={form.ebs_volumes} onChange={set("ebs_volumes")} placeholder={"/dev/sdf:100:gp3\n/dev/sdg:500:io2"} />
          </Field>

          <Section title="DNS & SRV" />
          <Field label="DNS Records (one per line)">
            <Textarea data-testid="form-dns" className={`${inputCls} min-h-[100px]`} value={form.dns_records} onChange={set("dns_records")} placeholder="db.analytics.asdex.com" />
          </Field>
          <Field label="SRV Records (one per line)">
            <Textarea data-testid="form-srv" className={`${inputCls} min-h-[100px]`} value={form.srv_records} onChange={set("srv_records")} placeholder="srv.analytics.asdex.com" />
          </Field>

          <Section title="Tags & Metadata" />
          <Field label="AWS Tags (key=value per line)" hint="Team=data">
            <Textarea data-testid="form-tags" className={`${inputCls} min-h-[80px]`} value={form.tags} onChange={set("tags")} placeholder={"Team=data\nCostCenter=1234"} />
          </Field>
          <Field label="Custom Metadata (key=value per line)">
            <Textarea data-testid="form-custom" className={`${inputCls} min-h-[80px]`} value={form.custom_metadata} onChange={set("custom_metadata")} placeholder={"owner=alice\nbackup=daily"} />
          </Field>
          <Field label="Notes" full>
            <Textarea className={inputCls} value={form.notes} onChange={set("notes")} />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</Button>
          <Button data-testid="form-save-button" onClick={submit} disabled={saving} className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm">
            {saving ? "Saving..." : "Save Instance"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
