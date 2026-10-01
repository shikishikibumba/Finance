import { useState, useEffect, useCallback } from "react";
import API from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Filter, RefreshCw, Receipt, Banknote } from "lucide-react";

const STATUS_STYLES = {
  "Available": "bg-blue-100 text-blue-800 border-blue-200",
  "Issued to Supplier": "bg-amber-100 text-amber-800 border-amber-200",
  "Deposited": "bg-slate-100 text-slate-800 border-slate-200",
  "Cleared": "bg-emerald-100 text-emerald-800 border-emerald-200",
  "Bounced": "bg-red-100 text-red-800 border-red-200",
};
const STATUSES = ["Available", "Issued to Supplier", "Deposited", "Cleared", "Bounced"];

const fmtLKR = (n) => "Rs. " + Number(n || 0).toLocaleString("en-LK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtDate = (iso) => { if (!iso) return "—"; try { return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); } catch { return iso; } };

export default function ChequeInventoryPage() {
  const [cheques, setCheques] = useState([]);
  const [banks, setBanks] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [filters, setFilters] = useState({
    status: "", bank: "", customer_id: "", supplier_id: "",
    min_amount: "", max_amount: "", date_from: "", date_to: "",
  });
  const [sort, setSort] = useState("date_desc");

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    cheque_number: "", bank: "", amount: "", cheque_date: "", notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
      params.set("sort", sort);
      const { data } = await API.get(`/cheque-inventory?${params.toString()}`);
      setCheques(data);
    } catch (e) { console.error(e); toast.error("Failed to load cheques"); }
    finally { setLoading(false); }
  }, [filters, sort]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    API.get("/banks").then((r) => setBanks(r.data)).catch(() => {});
    API.get("/customers").then((r) => setCustomers(r.data)).catch(() => {});
    API.get("/suppliers").then((r) => setSuppliers(r.data)).catch(() => {});
  }, []);

  const changeStatus = async (id, status) => {
    try {
      await API.patch(`/cheque-inventory/${id}/status`, { status });
      toast.success("Status updated");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to update status");
    }
  };

  const addOwn = async () => {
    try {
      await API.post("/cheque-inventory/own", {
        ...form,
        amount: Number(form.amount || 0),
      });
      toast.success("Own cheque added");
      setForm({ cheque_number: "", bank: "", amount: "", cheque_date: "", notes: "" });
      setShowAdd(false);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add cheque");
    }
  };

  const clearFilters = () => setFilters({
    status: "", bank: "", customer_id: "", supplier_id: "",
    min_amount: "", max_amount: "", date_from: "", date_to: "",
  });

  const totalAmount = cheques.reduce((s, c) => s + Number(c.amount || 0), 0);
  const availableCount = cheques.filter((c) => c.status === "Available").length;
  const issuedCount = cheques.filter((c) => c.status === "Issued to Supplier").length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ fontFamily: "Outfit, sans-serif" }}>Cheque Inventory</h1>
          <p className="text-sm text-muted-foreground mt-1">Full traceability · receipt → endorsement → deposit → clearance</p>
        </div>
        <Dialog open={showAdd} onOpenChange={setShowAdd}>
          <DialogTrigger asChild>
            <Button data-testid="add-own-cheque-btn" className="gap-2"><Plus size={16} /> Add Own Cheque</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Own Cheque</DialogTitle>
              <p className="text-sm text-muted-foreground">Cheque retained by us for future deposit into our own accounts</p>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2"><Label>Cheque # *</Label><Input data-testid="own-chq-number" value={form.cheque_number} onChange={(e) => setForm({ ...form, cheque_number: e.target.value })} /></div>
              <div className="col-span-2"><Label>Bank *</Label>
                <Select value={form.bank} onValueChange={(v) => setForm({ ...form, bank: v })}>
                  <SelectTrigger data-testid="own-chq-bank"><SelectValue placeholder="Select bank" /></SelectTrigger>
                  <SelectContent>{banks.map((b) => <SelectItem key={b.id} value={b.name}>{b.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Amount *</Label><Input type="number" step="0.01" data-testid="own-chq-amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
              <div><Label>Cheque Date *</Label><Input type="date" data-testid="own-chq-date" value={form.cheque_date} onChange={(e) => setForm({ ...form, cheque_date: e.target.value })} /></div>
              <div className="col-span-2"><Label>Notes</Label><Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button data-testid="own-chq-save" onClick={addOwn}>Save</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card><CardContent className="p-4"><div className="text-xs text-muted-foreground uppercase tracking-wider">Total Cheques</div><div className="text-2xl font-semibold mt-1 tabular-nums">{cheques.length}</div></CardContent></Card>
        <Card><CardContent className="p-4"><div className="text-xs text-muted-foreground uppercase tracking-wider">Available</div><div className="text-2xl font-semibold mt-1 tabular-nums">{availableCount}</div></CardContent></Card>
        <Card><CardContent className="p-4"><div className="text-xs text-muted-foreground uppercase tracking-wider">Issued to Supplier</div><div className="text-2xl font-semibold mt-1 tabular-nums">{issuedCount}</div></CardContent></Card>
        <Card><CardContent className="p-4"><div className="text-xs text-muted-foreground uppercase tracking-wider">Total Value</div><div className="text-2xl font-semibold mt-1 tabular-nums">{fmtLKR(totalAmount)}</div></CardContent></Card>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm flex items-center gap-2"><Filter size={14} /> Filters & Sort</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><Label className="text-xs">Status</Label>
            <Select value={filters.status || "all"} onValueChange={(v) => setFilters({ ...filters, status: v === "all" ? "" : v })}>
              <SelectTrigger data-testid="ci-status-filter"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All</SelectItem>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Bank</Label>
            <Select value={filters.bank || "all"} onValueChange={(v) => setFilters({ ...filters, bank: v === "all" ? "" : v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All</SelectItem>{banks.map((b) => <SelectItem key={b.id} value={b.name}>{b.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Customer</Label>
            <Select value={filters.customer_id || "all"} onValueChange={(v) => setFilters({ ...filters, customer_id: v === "all" ? "" : v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All</SelectItem>{customers.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Supplier</Label>
            <Select value={filters.supplier_id || "all"} onValueChange={(v) => setFilters({ ...filters, supplier_id: v === "all" ? "" : v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All</SelectItem>{suppliers.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Min Amount</Label><Input type="number" step="0.01" value={filters.min_amount} onChange={(e) => setFilters({ ...filters, min_amount: e.target.value })} /></div>
          <div><Label className="text-xs">Max Amount</Label><Input type="number" step="0.01" value={filters.max_amount} onChange={(e) => setFilters({ ...filters, max_amount: e.target.value })} /></div>
          <div><Label className="text-xs">From Date</Label><Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} /></div>
          <div><Label className="text-xs">To Date</Label><Input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} /></div>
          <div className="col-span-2 md:col-span-4 flex items-end gap-2">
            <div className="flex-1"><Label className="text-xs">Sort</Label>
              <Select value={sort} onValueChange={setSort}>
                <SelectTrigger data-testid="ci-sort"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="date_desc">Cheque Date (Newest)</SelectItem>
                  <SelectItem value="date_asc">Cheque Date (Oldest)</SelectItem>
                  <SelectItem value="customer">Customer</SelectItem>
                  <SelectItem value="supplier">Supplier</SelectItem>
                  <SelectItem value="amount_desc">Amount (High)</SelectItem>
                  <SelectItem value="amount_asc">Amount (Low)</SelectItem>
                  <SelectItem value="bank">Bank</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button variant="outline" onClick={clearFilters}>Clear</Button>
          </div>
        </CardContent>
      </Card>

      {/* Cheques table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-muted-foreground">Loading…</div>
          ) : cheques.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <Receipt size={32} className="mx-auto mb-2 opacity-50" />
              <div>No cheques found</div>
              <p className="text-xs mt-1">Cheques appear here automatically when a customer pays by cheque.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cheque #</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead>Bank</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Cheque Date</TableHead>
                  <TableHead>Received</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cheques.map((c) => (
                  <TableRow key={c.id} data-testid={`cheque-row-${c.id}`}>
                    <TableCell className="font-mono">{c.cheque_number}</TableCell>
                    <TableCell>{c.customer_name || "—"}</TableCell>
                    <TableCell>{c.supplier_name || "—"}</TableCell>
                    <TableCell>{c.bank}</TableCell>
                    <TableCell className="text-right tabular-nums font-medium">{fmtLKR(c.amount)}</TableCell>
                    <TableCell className="tabular-nums text-muted-foreground text-sm">{fmtDate(c.cheque_date)}</TableCell>
                    <TableCell className="tabular-nums text-muted-foreground text-sm">{fmtDate(c.received_date)}</TableCell>
                    <TableCell>
                      <Select value={c.status} onValueChange={(v) => changeStatus(c.id, v)}>
                        <SelectTrigger className="h-8 w-40" data-testid={`chq-status-${c.id}`}>
                          <SelectValue>
                            <Badge className={`${STATUS_STYLES[c.status] || ""} font-normal`}>{c.status}</Badge>
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                      </Select>
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
