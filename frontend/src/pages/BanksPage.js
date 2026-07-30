import { useState, useEffect, useCallback } from "react";
import API from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Trash2, Banknote } from "lucide-react";

export default function BanksPage() {
  const [banks, setBanks] = useState([]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setBanks((await API.get("/banks")).data); }
    catch (e) { toast.error("Failed to load banks"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    try {
      await API.post("/banks", { name });
      toast.success("Bank added");
      setName(""); setOpen(false); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const remove = async (b) => {
    if (b.seeded) { toast.error("Seeded banks cannot be deleted"); return; }
    if (!window.confirm(`Delete bank '${b.name}'?`)) return;
    try {
      await API.delete(`/banks/${b.id}`);
      toast.success("Bank deleted");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ fontFamily: "Outfit, sans-serif" }}>Banks</h1>
          <p className="text-sm text-muted-foreground mt-1">Sri Lankan bank list used across payments and cheques</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="add-bank-btn" className="gap-2"><Plus size={16} /> Add Bank</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Add Bank</DialogTitle></DialogHeader>
            <div>
              <Label>Bank Name *</Label>
              <Input autoFocus data-testid="bank-name-input" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button data-testid="save-bank-btn" onClick={add}>Save</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-muted-foreground">Loading…</div>
          ) : banks.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <Banknote size={32} className="mx-auto mb-2 opacity-50" />
              <div>No banks</div>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Bank Name</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="w-16"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {banks.map((b) => (
                  <TableRow key={b.id} data-testid={`bank-row-${b.id}`}>
                    <TableCell className="font-medium">{b.name}</TableCell>
                    <TableCell>
                      {b.seeded
                        ? <Badge variant="outline" className="font-normal">Seeded</Badge>
                        : <Badge className="bg-blue-100 text-blue-800 border-blue-200 font-normal">User-added</Badge>}
                    </TableCell>
                    <TableCell>
                      {!b.seeded && (
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => remove(b)} data-testid={`delete-bank-${b.id}`}>
                          <Trash2 size={14} className="text-red-600" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
