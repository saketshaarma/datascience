import { useEffect, useState, useCallback } from "react";
import { Plus, Upload, Search, Pencil, Trash2, Server, Download, Trash } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PageHeader } from "@/components/PageHeader";
import { InstanceForm } from "@/components/InstanceForm";
import { CsvUpload } from "@/components/CsvUpload";
import { getInstances, deleteInstance, deleteAllInstances, downloadCsv } from "@/lib/api";
import { toast } from "sonner";

const roleColor = (r) => {
  const v = (r || "").toLowerCase();
  if (v.includes("master")) return "bg-blue-500/15 text-blue-400 border-blue-500/30";
  if (v.includes("slave")) return "bg-orange-500/15 text-orange-400 border-orange-500/30";
  return "bg-zinc-500/15 text-zinc-400 border-zinc-500/30";
};

export default function Inventory() {
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [csvOpen, setCsvOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [toDelete, setToDelete] = useState(null);
  const [wipeOpen, setWipeOpen] = useState(false);

  const load = useCallback(async (q) => {
    setLoading(true);
    try {
      setItems(await getInstances(q));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => load(search), 300);
    return () => clearTimeout(t);
  }, [search, load]);

  const confirmDelete = async () => {
    await deleteInstance(toDelete.id);
    toast.success("Instance deleted");
    setToDelete(null);
    load(search);
  };

  const confirmWipe = async () => {
    try {
      const res = await deleteAllInstances();
      toast.success(`Deleted ${res.deleted} instances`);
    } catch (e) {
      toast.error("Delete failed");
    }
    setWipeOpen(false);
    load(search);
  };

  const doExport = async () => {
    if (items.length === 0) {
      toast.error("Nothing to export");
      return;
    }
    try {
      await downloadCsv();
      toast.success("Inventory exported");
    } catch (e) {
      toast.error("Export failed");
    }
  };

  return (
    <div>
      <PageHeader
        title="Inventory"
        subtitle="Central source of truth for infrastructure metadata"
        actions={
          <>
            <Button
              data-testid="export-csv-button"
              variant="outline"
              onClick={doExport}
              className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm gap-2"
            >
              <Download className="h-4 w-4" /> Export
            </Button>
            <Button
              data-testid="open-csv-upload"
              variant="outline"
              onClick={() => setCsvOpen(true)}
              className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm gap-2"
            >
              <Upload className="h-4 w-4" /> Upload CSV
            </Button>
            <Button
              data-testid="add-instance-button"
              onClick={() => { setEditing(null); setFormOpen(true); }}
              className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2"
            >
              <Plus className="h-4 w-4" /> Add Instance
            </Button>
          </>
        }
      />

      <div className="p-8 space-y-4">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
          <Input
            data-testid="inventory-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search host, name, role, DNS..."
            className="pl-9 bg-[#18181B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2"
          />
        </div>

        <div className="bg-[#18181B] border border-[#27272A] rounded-sm overflow-hidden">
          <table className="w-full text-sm" data-testid="inventory-table">
            <thead>
              <tr className="border-b border-[#27272A] text-left text-[11px] uppercase tracking-wider text-zinc-500">
                <th className="px-4 py-3 font-medium">Instance</th>
                <th className="px-4 py-3 font-medium">Env</th>
                <th className="px-4 py-3 font-medium">Host : Port</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">EC2 Type</th>
                <th className="px-4 py-3 font-medium">AMI</th>
                <th className="px-4 py-3 font-medium text-center">DNS</th>
                <th className="px-4 py-3 font-medium text-center">SRV</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={9} className="px-4 py-10 text-center text-zinc-600">Loading…</td></tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-16">
                    <div className="flex flex-col items-center gap-3 border border-dashed border-white/10 rounded-sm py-10">
                      <Server className="h-8 w-8 text-zinc-700" />
                      <p className="text-zinc-500 text-sm">No instances yet</p>
                      <p className="text-zinc-600 text-xs">Add one manually or upload your CSV</p>
                    </div>
                  </td>
                </tr>
              ) : (
                items.map((it) => (
                  <tr key={it.id} data-testid={`inventory-row-${it.id}`} className="border-b border-[#27272A]/60 hover:bg-white/5 transition-colors duration-150">
                    <td className="px-4 py-3 text-white font-medium">{it.instance_name || "—"}</td>
                    <td className="px-4 py-3">
                      {it.environment ? (
                        <span className="font-mono text-[11px] text-zinc-400">{it.environment}</span>
                      ) : <span className="text-zinc-600">—</span>}
                    </td>
                    <td className="px-4 py-3 font-mono text-zinc-300">
                      {it.host || "—"}{it.port ? <span className="text-zinc-500">:{it.port}</span> : ""}
                    </td>
                    <td className="px-4 py-3">
                      {it.instance_role ? (
                        <Badge variant="outline" className={`rounded-sm font-mono text-[11px] ${roleColor(it.instance_role)}`}>
                          {it.instance_role}
                        </Badge>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-zinc-400">{it.ec2_instance_type || "—"}</td>
                    <td className="px-4 py-3 font-mono text-zinc-500 text-xs max-w-[140px] truncate">{it.ami_id || "—"}</td>
                    <td className="px-4 py-3 text-center font-mono text-zinc-300">{(it.dns_records || []).length}</td>
                    <td className="px-4 py-3 text-center font-mono text-zinc-300">{(it.srv_records || []).length}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          data-testid={`edit-${it.id}`}
                          onClick={() => { setEditing(it); setFormOpen(true); }}
                          className="p-1.5 rounded-sm text-zinc-500 hover:text-white hover:bg-white/10 transition-colors duration-150"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          data-testid={`delete-${it.id}`}
                          onClick={() => setToDelete(it)}
                          className="p-1.5 rounded-sm text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors duration-150"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between">
          <p className="text-xs text-zinc-600 font-mono">{items.length} instance(s)</p>
          {items.length > 0 && (
            <button
              data-testid="delete-all-button"
              onClick={() => setWipeOpen(true)}
              className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-red-400 transition-colors duration-150"
            >
              <Trash className="h-3.5 w-3.5" /> Delete all
            </button>
          )}
        </div>
      </div>

      <InstanceForm open={formOpen} onOpenChange={setFormOpen} instance={editing} onSaved={() => load(search)} />
      <CsvUpload open={csvOpen} onOpenChange={setCsvOpen} onImported={() => load(search)} />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent className="bg-[#18181B] border-[#27272A] text-white">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-head">Delete instance?</AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              This will permanently remove <span className="font-mono text-white">{toDelete?.instance_name || toDelete?.host}</span> and its records.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-delete" onClick={confirmDelete} className="bg-red-500 hover:bg-red-600 text-white rounded-sm">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={wipeOpen} onOpenChange={setWipeOpen}>
        <AlertDialogContent className="bg-[#18181B] border-[#27272A] text-white">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-head">Delete ALL instances?</AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              This permanently removes every instance and all their DNS/SRV records. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-delete-all" onClick={confirmWipe} className="bg-red-500 hover:bg-red-600 text-white rounded-sm">Delete everything</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
