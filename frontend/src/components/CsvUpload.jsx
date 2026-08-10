import { useState } from "react";
import { UploadCloud, FileSpreadsheet, X } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { importCsv } from "@/lib/api";
import { toast } from "sonner";

export const CsvUpload = ({ open, onOpenChange, onImported }) => {
  const [file, setFile] = useState(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);

  const pick = (f) => {
    if (f && f.name.toLowerCase().endsWith(".csv")) setFile(f);
    else toast.error("Please select a .csv file");
  };

  const doImport = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const res = await importCsv(file);
      toast.success(`Imported ${res.imported} instances`);
      setFile(null);
      onImported();
      onOpenChange(false);
    } catch (e) {
      toast.error("Import failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#18181B] border-[#27272A] text-white">
        <DialogHeader>
          <DialogTitle className="font-head">Bulk Upload CSV</DialogTitle>
        </DialogHeader>
        <div
          data-testid="csv-dropzone"
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            pick(e.dataTransfer.files?.[0]);
          }}
          className={`rounded-sm border-2 border-dashed p-10 text-center transition-colors duration-150 ${
            drag ? "border-orange-500 bg-orange-500/5" : "border-white/15"
          }`}
        >
          {file ? (
            <div className="flex items-center justify-center gap-3">
              <FileSpreadsheet className="h-6 w-6 text-orange-500" />
              <span className="font-mono text-sm">{file.name}</span>
              <button onClick={() => setFile(null)} className="text-zinc-500 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <>
              <UploadCloud className="h-8 w-8 text-zinc-500 mx-auto mb-3" strokeWidth={1.5} />
              <p className="text-sm text-zinc-400">Drag & drop your CSV here, or</p>
              <label className="inline-block mt-2 cursor-pointer text-orange-500 text-sm font-medium hover:underline">
                browse files
                <input
                  data-testid="csv-file-input"
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => pick(e.target.files?.[0])}
                />
              </label>
              <p className="text-[11px] text-zinc-600 mt-3 font-mono">
                Columns: InstanceName, Host_Port, Instance Type, ALL_DNS, SRV
              </p>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="border-white/20 bg-transparent text-white hover:bg-white/10 rounded-sm">
            Cancel
          </Button>
          <Button data-testid="csv-import-button" onClick={doImport} disabled={!file || busy} className="bg-orange-500 hover:bg-orange-600 text-white rounded-sm">
            {busy ? "Importing..." : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
