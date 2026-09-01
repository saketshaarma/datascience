import { useEffect, useState } from "react";
import { UserPlus, Trash2, Shield, User, Cloud, Save } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { PageHeader } from "@/components/PageHeader";
import {
  listUsers, createUser, deleteUser, formatApiErrorDetail,
  getAwsSettings, saveAwsSettings,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const inputCls =
  "bg-[#09090B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2";

export default function Team() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [toDelete, setToDelete] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);

  const load = () => listUsers().then(setUsers).catch(() => {});
  useEffect(() => { load(); }, []);

  const submit = async () => {
    setBusy(true);
    try {
      await createUser(form);
      toast.success("Account created");
      setForm({ name: "", email: "", password: "" });
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    try {
      await deleteUser(toDelete.id);
      toast.success("Account removed");
      setToDelete(null);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div>
      <PageHeader
        title="Team"
        subtitle="Manage who can access the portal"
        actions={
          isAdmin && (
            <Button data-testid="add-user-button" onClick={() => setOpen(true)}
              className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2">
              <UserPlus className="h-4 w-4" /> Add Member
            </Button>
          )
        }
      />
      <div className="p-8">
        {isAdmin && <AwsSettingsCard />}
        <div className="bg-[#18181B] border border-[#27272A] rounded-sm overflow-hidden max-w-3xl">
          <table className="w-full text-sm" data-testid="team-table">
            <thead>
              <tr className="border-b border-[#27272A] text-left text-[11px] uppercase tracking-wider text-zinc-500">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-[#27272A]/60 hover:bg-white/5 transition-colors duration-150">
                  <td className="px-4 py-3 text-white">{u.name || "—"}</td>
                  <td className="px-4 py-3 font-mono text-zinc-300">{u.email}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline" className={`rounded-sm gap-1 font-mono text-[11px] ${u.role === "admin" ? "bg-orange-500/15 text-orange-400 border-orange-500/30" : "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"}`}>
                      {u.role === "admin" ? <Shield className="h-3 w-3" /> : <User className="h-3 w-3" />}
                      {u.role}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {isAdmin && u.id !== user.id && (
                      <button data-testid={`delete-user-${u.id}`} onClick={() => setToDelete(u)}
                        className="p-1.5 rounded-sm text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors duration-150">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!isAdmin && <p className="text-xs text-zinc-600 mt-3">Only admins can add or remove members.</p>}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-[#18181B] border-[#27272A] text-white">
          <DialogHeader><DialogTitle className="font-head">Add Team Member</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-zinc-400">Name</Label>
              <Input data-testid="user-name" className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-zinc-400">Email</Label>
              <Input data-testid="user-email" type="email" className={inputCls} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-zinc-400">Password</Label>
              <Input data-testid="user-password" type="password" className={inputCls} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</Button>
            <Button data-testid="user-save-button" onClick={submit} disabled={busy} className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm">
              {busy ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent className="bg-[#18181B] border-[#27272A] text-white">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-head">Remove member?</AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              <span className="font-mono text-white">{toDelete?.email}</span> will lose access to the portal.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-delete-user" onClick={confirmDelete} className="bg-red-500 hover:bg-red-600 text-white rounded-sm">Remove</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}


const inputClsAws =
  "bg-[#09090B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2";

const AwsSettingsCard = () => {
  const [form, setForm] = useState({ access_key_id: "", secret_access_key: "", region: "us-east-1", use_live: false });
  const [info, setInfo] = useState({ configured: false, access_key_id_masked: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAwsSettings().then((s) => {
      setInfo(s);
      setForm((f) => ({ ...f, region: s.region || "us-east-1", use_live: s.use_live }));
    }).catch(() => {});
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      const res = await saveAwsSettings(form);
      toast.success("AWS settings saved");
      setForm((f) => ({ ...f, access_key_id: "", secret_access_key: "" }));
      const s = await getAwsSettings();
      setInfo(s);
      setForm((f) => ({ ...f, use_live: s.use_live, region: s.region }));
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="aws-settings-card" className="bg-[#18181B] border border-[#27272A] rounded-sm p-5 max-w-3xl mb-6">
      <div className="flex items-center gap-2 mb-1">
        <Cloud className="h-4 w-4 text-orange-500" />
        <h3 className="font-head font-semibold text-sm text-white">AWS Connection</h3>
        <Badge variant="outline" className={`ml-2 rounded-sm font-mono text-[10px] ${info.configured ? "bg-green-500/15 text-green-400 border-green-500/30" : "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"}`}>
          {info.configured ? "configured" : "not set"}
        </Badge>
      </div>
      <p className="text-xs text-zinc-500 mb-4">
        Used by the Discovery Dashboard. Leave demo mode off to keep using mock discovery.
        {info.configured && <> Current key: <span className="font-mono text-zinc-400">{info.access_key_id_masked}</span></>}
      </p>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label className="text-xs text-zinc-400">AWS Access Key ID</Label>
          <Input data-testid="aws-access-key" className={inputClsAws} value={form.access_key_id} onChange={(e) => setForm({ ...form, access_key_id: e.target.value })} placeholder={info.configured ? "•••• (unchanged)" : "AKIA..."} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-zinc-400">AWS Secret Access Key</Label>
          <Input data-testid="aws-secret-key" type="password" className={inputClsAws} value={form.secret_access_key} onChange={(e) => setForm({ ...form, secret_access_key: e.target.value })} placeholder={info.configured ? "•••• (unchanged)" : "secret"} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-zinc-400">Default Region</Label>
          <Input data-testid="aws-region" className={inputClsAws} value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} placeholder="ap-south-2" />
        </div>
        <div className="flex items-center gap-3 pt-6">
          <Switch data-testid="aws-use-live" checked={form.use_live} onCheckedChange={(v) => setForm({ ...form, use_live: v })} />
          <div>
            <div className="text-sm text-white">Live discovery</div>
            <div className="text-[11px] text-zinc-500">Off = demo/mock mode</div>
          </div>
        </div>
      </div>
      <div className="flex justify-end mt-4">
        <Button data-testid="aws-save-settings" onClick={save} disabled={busy} className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2">
          <Save className="h-4 w-4" /> {busy ? "Saving…" : "Save AWS settings"}
        </Button>
      </div>
    </div>
  );
};
