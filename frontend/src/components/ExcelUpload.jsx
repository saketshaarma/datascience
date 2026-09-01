import { useState } from "react";
import { UploadCloud, FileSpreadsheet, X } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { importDbExcel } from "@/lib/api";
import { toast } from "sonner";

export const ExcelUpload = ({ open, onOpenChange, onImported }) => {
  const [file, setFile] = useState(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);

  const pick = (f) => {
    if (f && f.name.toLowerCase().endsWith(".xlsx")) setFile(f);
    else toast.error("Please select a .xlsx file");
  };

  const doImport = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const res = await importDbExcel(file);
      const msg = res.skipped
        ? `Imported ${res.imported} instances (${res.skipped} skipped)`
        : `Imported ${res.imported} instances`;
      toast.success(msg);
      setFile(null);
      onImported();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#18181B] border-[#27272A] text-white">
        <DialogHeader>
          <DialogTitle className="font-head">Upload Excel</DialogTitle>
        </DialogHeader>
        <div
          data-testid="excel-dropzone"
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); }}
          className={`rounded-sm border-2 border-dashed p-10 text-center transition-colors duration-150 ${drag ? "border-orange-500 bg-orange-500/5" : "border-white/15"}`}
        >
          {file ? (
            <div className="flex items-center justify-center gap-3">
              <FileSpreadsheet className="h-6 w-6 text-orange-500" />
              <span className="font-mono text-sm">{file.name}</span>
              <button onClick={() => setFile(null)} className="text-zinc-500 hover:text-white"><X className="h-4 w-4" /></button>
            </div>
          ) : (
            <>
              <UploadCloud className="h-8 w-8 text-zinc-500 mx-auto mb-3" strokeWidth={1.5} />
              <p className="text-sm text-zinc-400">Drag & drop your .xlsx here, or</p>
              <label className="inline-block mt-2 cursor-pointer text-orange-500 text-sm font-medium hover:underline">
                browse files
                <input data-testid="excel-file-input" type="file" accept=".xlsx" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
              </label>
              <p className="text-[11px] text-zinc-600 mt-3 font-mono">
                Columns: service_name, instance_name, host, port, instance_type,<br />
                aws_instance_id, all_dns, srv_record, aws_region, environment, status
              </p>
              <p className="text-[11px] text-zinc-600 mt-1 font-mono">Any extra columns become metadata attributes.</p>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">Cancel</Button>
          <Button data-testid="excel-import-button" onClick={doImport} disabled={!file || busy} className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm">
            {busy ? "Importing..." : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
