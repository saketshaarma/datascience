import { useEffect, useState, useCallback } from "react";
import {
  Plus, Upload, Search, Pencil, Trash2, Database, FileJson, Server, Check, Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PageHeader } from "@/components/PageHeader";
import { DbInstanceForm } from "@/components/DbInstanceForm";
import { ExcelUpload } from "@/components/ExcelUpload";
import {
  listDbServices, createDbService, deleteDbService,
  listDbInstances, deleteDbInstance, exportDbJson, exportCombinedJson,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const envColor = (e) => ({
  PROD: "bg-red-500/15 text-red-400 border-red-500/30",
  DR: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  UAT: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  QA: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  DEV: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
}[e] || "bg-zinc-500/15 text-zinc-400 border-zinc-500/30");

const statusColor = (s) => ({
  Running: "bg-green-500/15 text-green-400 border-green-500/30",
  Stopped: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  Terminated: "bg-red-500/15 text-red-400 border-red-500/30",
}[s] || "bg-zinc-500/15 text-zinc-400 border-zinc-500/30");

export default function DbConfig() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [services, setServices] = useState([]);
  const [instances, setInstances] = useState([]);
  const [activeService, setActiveService] = useState(null); // null = all
  const [search, setSearch] = useState("");
  const [newSvc, setNewSvc] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [excelOpen, setExcelOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [toDelete, setToDelete] = useState(null);
  const [svcToDelete, setSvcToDelete] = useState(null);

  const loadServices = useCallback(async () => setServices(await listDbServices()), []);
  const loadInstances = useCallback(async () => {
    const params = {};
    if (activeService) params.service_id = activeService;
    if (search) params.search = search;
    setInstances(await listDbInstances(params));
  }, [activeService, search]);

  useEffect(() => { loadServices(); }, [loadServices]);
  useEffect(() => {
    const t = setTimeout(() => loadInstances(), 250);
    return () => clearTimeout(t);
  }, [loadInstances]);

  const addService = async () => {
    if (!newSvc.trim()) return;
    try {
      await createDbService({ service_name: newSvc.trim() });
      toast.success("Service added");
      setNewSvc("");
      loadServices();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const confirmDelete = async () => {
    await deleteDbInstance(toDelete.id);
    toast.success("Instance deleted");
    setToDelete(null);
    loadInstances();
    loadServices();
  };

  const confirmDeleteSvc = async () => {
    try {
      await deleteDbService(svcToDelete.id);
      toast.success("Service deleted");
      if (activeService === svcToDelete.id) setActiveService(null);
      loadServices();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
    setSvcToDelete(null);
  };

  const doExport = async () => {
    try {
      await exportDbJson();
      toast.success("Exported db_config.json");
    } catch (e) {
      toast.error("Export failed");
    }
  };

  const doExportCombined = async () => {
    try {
      await exportCombinedJson();
      toast.success("Exported combined JSON (DB + Kubernetes + Workloads)");
    } catch (e) {
      toast.error("Combined export failed");
    }
  };

  return (
    <div>
      <PageHeader
        title="DB Config"
        subtitle="Database services, instances & metadata"
        actions={
          <>
            <Button data-testid="db-export-combined" variant="outline" onClick={doExportCombined}
              className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm gap-2">
              <Layers className="h-4 w-4" /> Combined JSON
            </Button>
            <Button data-testid="db-export-json" variant="outline" onClick={doExport}
              className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm gap-2">
              <FileJson className="h-4 w-4" /> Export JSON
            </Button>
            <Button data-testid="db-upload-excel" variant="outline" onClick={() => setExcelOpen(true)}
              className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm gap-2">
              <Upload className="h-4 w-4" /> Upload Excel
            </Button>
            <Button data-testid="db-add-instance" onClick={() => { setEditing(null); setFormOpen(true); }}
              className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm gap-2">
              <Plus className="h-4 w-4" /> Add Instance
            </Button>
          </>
        }
      />

      <div className="p-8 grid grid-cols-1 xl:grid-cols-[240px_1fr] gap-6">
        {/* services */}
        <div className="space-y-2">
          <h3 className="font-head font-semibold text-[11px] uppercase tracking-wider text-zinc-500 mb-2">Services</h3>
          <button
            data-testid="db-service-all"
            onClick={() => setActiveService(null)}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-sm border text-sm transition-colors duration-150 ${
              activeService === null ? "bg-orange-500/10 border-orange-500/40 text-orange-300" : "bg-[#18181B] border-[#27272A] text-zinc-300 hover:bg-white/5"
            }`}
          >
            <span className="flex items-center gap-2"><Database className="h-3.5 w-3.5" /> All services</span>
          </button>
          {services.map((s) => (
            <div key={s.id} data-testid={`db-service-${s.id}`}
              onClick={() => setActiveService(s.id)}
              className={`group flex items-center justify-between px-3 py-2 rounded-sm border cursor-pointer text-sm transition-colors duration-150 ${
                activeService === s.id ? "bg-orange-500/10 border-orange-500/40 text-orange-300" : "bg-[#18181B] border-[#27272A] text-zinc-300 hover:bg-white/5"
              }`}>
              <span className="font-mono truncate">{s.service_name}</span>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-zinc-600">{s.instance_count}</span>
                {isAdmin && (
                  <button data-testid={`db-delete-service-${s.id}`} onClick={(e) => { e.stopPropagation(); setSvcToDelete(s); }}
                    className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 transition-opacity">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
          <div className="flex gap-2 pt-2">
            <Input data-testid="db-new-service" value={newSvc} onChange={(e) => setNewSvc(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addService()}
              placeholder="new service"
              className="bg-[#18181B] border-[#27272A] text-white font-mono text-xs h-9 focus-visible:ring-orange-500/50 focus-visible:ring-2" />
            <Button data-testid="db-add-service" onClick={addService} size="icon" className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm h-9 w-9 shrink-0">
              <Check className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* instances */}
        <div className="space-y-4">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <Input data-testid="db-search" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search instance, host, aws id, dns..."
              className="pl-9 bg-[#18181B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2" />
          </div>

          <div className="bg-[#18181B] border border-[#27272A] rounded-sm overflow-x-auto">
            <table className="w-full text-sm" data-testid="db-instances-table">
              <thead>
                <tr className="border-b border-[#27272A] text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-3 font-medium">Service</th>
                  <th className="px-4 py-3 font-medium">Instance</th>
                  <th className="px-4 py-3 font-medium">Host : Port</th>
                  <th className="px-4 py-3 font-medium">AWS ID</th>
                  <th className="px-4 py-3 font-medium">Region</th>
                  <th className="px-4 py-3 font-medium">Env</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium text-center">Meta</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {instances.length === 0 ? (
                  <tr><td colSpan={9} className="px-4 py-16">
                    <div className="flex flex-col items-center gap-3 border border-dashed border-white/10 rounded-sm py-10">
                      <Server className="h-8 w-8 text-zinc-700" />
                      <p className="text-zinc-500 text-sm">No DB instances</p>
                      <p className="text-zinc-600 text-xs">Add one or upload an Excel file</p>
                    </div>
                  </td></tr>
                ) : instances.map((it) => (
                  <tr key={it.id} data-testid={`db-row-${it.id}`} className="border-b border-[#27272A]/60 hover:bg-white/5 transition-colors duration-150">
                    <td className="px-4 py-3 font-mono text-zinc-400">{it.service_name || "—"}</td>
                    <td className="px-4 py-3 text-white font-medium">{it.instance_name}</td>
                    <td className="px-4 py-3 font-mono text-zinc-300">{it.host}{it.port ? <span className="text-zinc-500">:{it.port}</span> : ""}</td>
                    <td className="px-4 py-3 font-mono text-zinc-500 text-xs">{it.aws_instance_id || "—"}</td>
                    <td className="px-4 py-3 font-mono text-zinc-400">{it.aws_region || "—"}</td>
                    <td className="px-4 py-3"><Badge variant="outline" className={`rounded-sm font-mono text-[11px] ${envColor(it.environment)}`}>{it.environment}</Badge></td>
                    <td className="px-4 py-3"><Badge variant="outline" className={`rounded-sm font-mono text-[11px] ${statusColor(it.status)}`}>{it.status}</Badge></td>
                    <td className="px-4 py-3 text-center font-mono text-zinc-300">{(it.metadata || []).length}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button data-testid={`db-edit-${it.id}`} onClick={() => { setEditing(it); setFormOpen(true); }}
                          className="p-1.5 rounded-sm text-zinc-500 hover:text-white hover:bg-white/10 transition-colors duration-150">
                          <Pencil className="h-4 w-4" />
                        </button>
                        {isAdmin && (
                          <button data-testid={`db-delete-${it.id}`} onClick={() => setToDelete(it)}
                            className="p-1.5 rounded-sm text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors duration-150">
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-zinc-600 font-mono">{instances.length} instance(s)</p>
        </div>
      </div>

      <DbInstanceForm open={formOpen} onOpenChange={setFormOpen} instance={editing} services={services}
        defaultServiceId={activeService} onSaved={() => { loadInstances(); loadServices(); }}
        onServicesChanged={loadServices} />
      <ExcelUpload open={excelOpen} onOpenChange={setExcelOpen} onImported={() => { loadInstances(); loadServices(); }} />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent className="bg-[#18181B] border-[#27272A] text-white">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-head">Delete instance?</AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              <span className="font-mono text-white">{toDelete?.instance_name}</span> and its metadata will be removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="db-confirm-delete" onClick={confirmDelete} className="bg-red-500 hover:bg-red-600 text-white rounded-sm">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!svcToDelete} onOpenChange={(o) => !o && setSvcToDelete(null)}>
        <AlertDialogContent className="bg-[#18181B] border-[#27272A] text-white">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-head">Delete service?</AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              <span className="font-mono text-white">{svcToDelete?.service_name}</span> will be removed (only if it has no instances).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="db-confirm-delete-service" onClick={confirmDeleteSvc} className="bg-red-500 hover:bg-red-600 text-white rounded-sm">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
