import { useState, useEffect, useCallback } from "react";
import API from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { FileClock, Trash2 } from "lucide-react";

export function DraftsDialog({ kind, onResume, buttonClassName }) {
  const [drafts, setDrafts] = useState([]);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const { data } = await API.get("/drafts", { params: { kind } });
      setDrafts(data);
    } catch { /* ignore */ }
  }, [kind]);

  useEffect(() => { refresh(); }, [refresh]);

  const del = async (id, e) => {
    e.stopPropagation();
    try { await API.delete(`/drafts/${id}`); toast.success("Draft deleted"); refresh(); }
    catch { toast.error("Failed to delete draft"); }
  };

  return (
    <>
      <Button
        type="button"
        variant="outline"
        onClick={() => { refresh(); setOpen(true); }}
        data-testid="open-drafts-button"
        className={`rounded-sm gap-1 ${buttonClassName || ""}`}
      >
        <FileClock size={14} /> Drafts{drafts.length ? ` (${drafts.length})` : ""}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md" data-testid="drafts-dialog">
          <DialogHeader><DialogTitle style={{ fontFamily: "Outfit, sans-serif" }}>Saved Drafts</DialogTitle></DialogHeader>
          {drafts.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">No saved drafts yet.</p>
          ) : (
            <div className="space-y-2 max-h-[60vh] overflow-y-auto">
              {drafts.map((d) => (
                <div
                  key={d.id}
                  className="flex items-center justify-between border rounded-sm p-2.5 hover:bg-muted/40 cursor-pointer"
                  data-testid={`draft-item-${d.id}`}
                  onClick={() => { onResume(d.data || {}, d.id); setOpen(false); }}
                >
                  <div>
                    <div className="font-medium text-sm">{d.label || "Untitled draft"}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {(d.updated_at || d.created_at || "").slice(0, 16).replace("T", " ")}
                      {(d.data?.items?.length ? ` · ${d.data.items.length} item(s)` : "")}
                    </div>
                  </div>
                  <div className="flex gap-2 items-center">
                    <span className="text-xs text-blue-600 font-medium">Resume</span>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={(e) => del(d.id, e)} data-testid={`delete-draft-${d.id}`}>
                      <Trash2 size={13} />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
