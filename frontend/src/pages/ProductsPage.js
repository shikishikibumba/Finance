import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import API from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { SearchableSelect } from "@/components/SearchableSelect";
import { toast } from "sonner";
import { Plus, Search, Pencil, Trash2, Package, History, TrendingUp, ArrowRight } from "lucide-react";

const fmt = (n) => new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);
const EMPTY = { name: "", unit: "pcs", selling_price: "", cost_price: "", category: "General", primary_supplier_id: "", primary_supplier_name: "" };

export default function ProductsPage() {
  const navigate = useNavigate();
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [historyDialog, setHistoryDialog] = useState({ open: false, product: null, price: [], sales: [], loading: false });
  const nameRef = useRef(null);
  const sellingRef = useRef(null);
  const costRef = useRef(null);
  const saveRef = useRef(null);

  const focusNext = (nextRef) => (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (nextRef === saveRef) saveRef.current?.click();
      else nextRef.current?.focus();
    }
  };

  const fetchProducts = useCallback(async () => {
    try {
      const { data } = await API.get("/products", { params: { search: search || undefined } });
      setProducts(data);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => { fetchProducts(); }, [fetchProducts]);
  useEffect(() => { API.get("/suppliers").then(r => setSuppliers(r.data)).catch(() => {}); }, []);

  const openNew = () => { setEditing(null); setForm(EMPTY); setDialogOpen(true); };
  const openEdit = (p) => {
    setEditing(p);
    setForm({
      name: p.name, unit: p.unit, selling_price: p.selling_price ?? "", cost_price: p.cost_price ?? "",
      category: p.category || "General", primary_supplier_id: p.primary_supplier_id || "", primary_supplier_name: p.primary_supplier_name || "",
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!form.name?.trim()) { toast.error("Product name is required"); return; }
    const payload = {
      name: form.name, unit: form.unit, category: form.category || "General",
      selling_price: form.selling_price === "" ? 0 : parseFloat(form.selling_price),
      cost_price: form.cost_price === "" ? 0 : parseFloat(form.cost_price),
      primary_supplier_id: form.primary_supplier_id || "",
      primary_supplier_name: form.primary_supplier_name || "",
    };
    try {
      if (editing) { await API.put(`/products/${editing.id}`, payload); toast.success("Product updated"); }
      else { await API.post("/products", payload); toast.success("Product created"); }
      setDialogOpen(false);
      fetchProducts();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to save"); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this product?")) return;
    try { await API.delete(`/products/${id}`); toast.success("Product deleted"); fetchProducts(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed to delete"); }
  };

  const openHistory = async (p) => {
    setHistoryDialog({ open: true, product: p, price: [], sales: [], loading: true });
    try {
      const [ph, sh] = await Promise.all([
        API.get(`/products/${p.id}/price-history`),
        API.get(`/products/${p.id}/sales-history`),
      ]);
      setHistoryDialog(d => ({ ...d, price: ph.data || [], sales: sh.data || [], loading: false }));
    } catch (err) { toast.error("Failed to load history"); setHistoryDialog(d => ({ ...d, loading: false })); }
  };

  const supplierOptions = suppliers.map(s => ({ value: s.id, label: s.name }));

  return (
    <div className="space-y-6" data-testid="products-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight" style={{ fontFamily: 'Outfit, sans-serif' }}>Products</h1>
          <p className="text-sm text-muted-foreground mt-1" data-testid="products-total-count">
            {products.length} product{products.length === 1 ? "" : "s"} in catalog
          </p>
        </div>
        <Button onClick={openNew} className="bg-[#0F172A] hover:bg-[#1E293B] rounded-sm gap-2" data-testid="add-product-button">
          <Plus size={16} /> Add Product
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input placeholder="Search products..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" data-testid="product-search-input" />
      </div>

      <Card className="border shadow-sm">
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-muted-foreground">Loading...</div>
          ) : products.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <Package size={32} className="mx-auto mb-2 opacity-30" />
              No products found. Add your first product.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table w-full">
                <thead><tr><th>Name</th><th>Category</th><th>Primary Supplier</th><th>Unit</th><th>Selling Price</th><th>Cost Price</th><th>Margin</th><th className="w-28">Actions</th></tr></thead>
                <tbody>
                  {products.map(p => {
                    const margin = p.selling_price > 0 && p.cost_price > 0 ? ((p.selling_price - p.cost_price) / p.selling_price * 100).toFixed(1) : "-";
                    return (
                      <tr key={p.id} data-testid={`product-row-${p.id}`}>
                        <td className="font-medium">{p.name}</td>
                        <td><Badge variant="secondary" className="rounded-full text-xs font-normal">{p.category || "General"}</Badge></td>
                        <td className="text-muted-foreground" data-testid={`product-supplier-${p.id}`}>{p.primary_supplier_name || "-"}</td>
                        <td>{p.unit}</td>
                        <td>{"Rs. "}{fmt(p.selling_price)}</td>
                        <td>{"Rs. "}{fmt(p.cost_price)}</td>
                        <td className={margin !== "-" && parseFloat(margin) > 0 ? "text-emerald-600" : ""}>{margin !== "-" ? `${margin}%` : "-"}</td>
                        <td>
                          <div className="flex gap-1">
                            <Button variant="ghost" size="icon" className="h-8 w-8" title="History" onClick={() => openHistory(p)} data-testid={`history-product-${p.id}`}><History size={14} /></Button>
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(p)} data-testid={`edit-product-${p.id}`}><Pencil size={14} /></Button>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => handleDelete(p.id)} data-testid={`delete-product-${p.id}`}><Trash2 size={14} /></Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create / Edit Product */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md" onOpenAutoFocus={() => setTimeout(() => nameRef.current?.focus(), 50)}>
          <DialogHeader><DialogTitle style={{ fontFamily: 'Outfit, sans-serif' }}>{editing ? "Edit Product" : "New Product"}</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label className="text-xs font-bold uppercase tracking-wider">Product Name *</Label>
              <Input ref={nameRef} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} onKeyDown={focusNext(sellingRef)} placeholder="e.g. WC, Basin, Tap" data-testid="product-name-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label className="text-xs font-bold uppercase tracking-wider">Category</Label>
                <Input value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))} placeholder="Ceramic, General..." data-testid="product-category-input" />
              </div>
              <div className="space-y-2">
                <Label className="text-xs font-bold uppercase tracking-wider">Unit</Label>
                <Input value={form.unit} onChange={e => setForm(f => ({ ...f, unit: e.target.value }))} placeholder="pcs, kg, m" data-testid="product-unit-input" />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-bold uppercase tracking-wider">Primary Supplier</Label>
              <SearchableSelect
                options={supplierOptions}
                value={form.primary_supplier_id}
                onSelect={(v) => setForm(f => ({ ...f, primary_supplier_id: v, primary_supplier_name: suppliers.find(s => s.id === v)?.name || "" }))}
                placeholder="Select supplier (optional)..."
                data-testid="product-supplier-select"
              />
              {form.primary_supplier_id && (
                <button type="button" className="text-[11px] text-muted-foreground underline" onClick={() => setForm(f => ({ ...f, primary_supplier_id: "", primary_supplier_name: "" }))} data-testid="clear-product-supplier">Clear supplier</button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label className="text-xs font-bold uppercase tracking-wider">Selling Price</Label>
                <Input ref={sellingRef} type="number" value={form.selling_price} onChange={e => setForm(f => ({ ...f, selling_price: e.target.value }))} onKeyDown={focusNext(costRef)} placeholder="Selling price" data-testid="product-selling-price-input" />
              </div>
              <div className="space-y-2">
                <Label className="text-xs font-bold uppercase tracking-wider">Cost Price</Label>
                <Input ref={costRef} type="number" value={form.cost_price} onChange={e => setForm(f => ({ ...f, cost_price: e.target.value }))} onKeyDown={focusNext(saveRef)} placeholder="Cost price" data-testid="product-cost-price-input" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} className="rounded-sm">Cancel</Button>
            <Button ref={saveRef} onClick={handleSave} className="bg-[#0F172A] hover:bg-[#1E293B] rounded-sm" data-testid="save-product-button">{editing ? "Update" : "Create"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Price + Sales History */}
      <Dialog open={historyDialog.open} onOpenChange={(v) => setHistoryDialog(d => ({ ...d, open: v }))}>
        <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="product-history-dialog">
          <DialogHeader>
            <DialogTitle style={{ fontFamily: 'Outfit, sans-serif' }}>{historyDialog.product?.name} — History</DialogTitle>
          </DialogHeader>
          <Tabs defaultValue="price" className="w-full">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="price" data-testid="tab-price-history"><TrendingUp size={14} className="mr-1" /> Price History</TabsTrigger>
              <TabsTrigger value="sales" data-testid="tab-sales-history"><History size={14} className="mr-1" /> Invoice History</TabsTrigger>
            </TabsList>

            <TabsContent value="price" className="mt-3">
              {historyDialog.loading ? <div className="p-6 text-center text-muted-foreground">Loading...</div> : (
                historyDialog.price.length === 0 ? <div className="p-6 text-center text-muted-foreground text-sm">No price revisions recorded.</div> : (
                  <table className="data-table w-full text-sm">
                    <thead><tr><th>Date</th><th>Old Price</th><th>New Price</th><th>Cost</th><th>User</th></tr></thead>
                    <tbody>
                      {historyDialog.price.map((h, i) => (
                        <tr key={i} data-testid={`price-history-row-${i}`}>
                          <td className="text-muted-foreground">{(h.date || "").slice(0, 10)}</td>
                          <td>{h.previous_price != null ? `Rs. ${fmt(h.previous_price)}` : "-"}</td>
                          <td className="font-medium">Rs. {fmt(h.new_price != null ? h.new_price : h.selling_price)}</td>
                          <td>Rs. {fmt(h.cost_price)}</td>
                          <td className="text-xs text-muted-foreground">{h.user_email || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              )}
            </TabsContent>

            <TabsContent value="sales" className="mt-3">
              {historyDialog.loading ? <div className="p-6 text-center text-muted-foreground">Loading...</div> : (
                historyDialog.sales.length === 0 ? <div className="p-6 text-center text-muted-foreground text-sm">This product has not been sold on any invoice yet.</div> : (
                  <table className="data-table w-full text-sm">
                    <thead><tr><th>Invoice #</th><th>Customer</th><th>Date</th><th>Qty</th><th>Selling Price</th><th>Amount</th></tr></thead>
                    <tbody>
                      {historyDialog.sales.map((r, i) => (
                        <tr key={i} data-testid={`sales-history-row-${i}`}>
                          <td className="font-medium">{r.invoice_number}</td>
                          <td>
                            {r.customer_id ? (
                              <button className="text-[#0F172A] hover:underline inline-flex items-center gap-1" onClick={() => { setHistoryDialog(d => ({ ...d, open: false })); navigate(`/customers/${r.customer_id}`); }} data-testid={`sales-history-customer-${i}`}>
                                {r.customer_name} <ArrowRight size={11} />
                              </button>
                            ) : r.customer_name}
                          </td>
                          <td className="text-muted-foreground">{(r.date || "").slice(0, 10)}</td>
                          <td>{r.quantity}</td>
                          <td>Rs. {fmt(r.unit_price)}</td>
                          <td className="font-medium">Rs. {fmt(r.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              )}
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </div>
  );
}
