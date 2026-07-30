import { useState, useEffect, useCallback, Fragment } from "react";
import API from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Warehouse, Search, Package, ChevronRight, ChevronDown } from "lucide-react";

const fmt = (n) => new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);
const qty = (n) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n || 0);

const SOURCE_COLORS = {
  "Opening Stock": "bg-blue-100 text-blue-800",
  "Customer Return": "bg-amber-100 text-amber-800",
  "Warehouse Purchase": "bg-emerald-100 text-emerald-800",
};

export default function WarehousePage() {
  const [data, setData] = useState({ items: [], grand_total_value: 0, total_units: 0, product_count: 0 });
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  const fetchStock = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await API.get("/warehouse/stock", { params: { search: search || undefined } });
      setData(data);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => { const t = setTimeout(fetchStock, 250); return () => clearTimeout(t); }, [fetchStock]);

  return (
    <div className="space-y-6" data-testid="warehouse-page">
      <div className="flex items-center gap-3">
        <Warehouse size={26} />
        <div>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight" style={{ fontFamily: 'Outfit, sans-serif' }}>Warehouse</h1>
          <p className="text-sm text-muted-foreground mt-1">On-hand stock from opening balances, customer returns and warehouse purchases.</p>
        </div>
      </div>

      {/* Valuation banner */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card className="border shadow-sm"><CardContent className="p-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">Total Stock Value</div>
          <div className="text-2xl font-semibold mt-1" data-testid="warehouse-total-value">Rs. {fmt(data.grand_total_value)}</div>
        </CardContent></Card>
        <Card className="border shadow-sm"><CardContent className="p-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">Products On Hand</div>
          <div className="text-2xl font-semibold mt-1" data-testid="warehouse-product-count">{data.product_count}</div>
        </CardContent></Card>
        <Card className="border shadow-sm"><CardContent className="p-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">Total Units</div>
          <div className="text-2xl font-semibold mt-1" data-testid="warehouse-total-units">{qty(data.total_units)}</div>
        </CardContent></Card>
      </div>

      <div className="relative max-w-sm">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input placeholder="Search by product name / code..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" data-testid="warehouse-search-input" />
      </div>

      <Card className="border shadow-sm">
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-muted-foreground">Loading...</div>
          ) : data.items.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <Package size={32} className="mx-auto mb-2 opacity-30" />
              No stock on hand{search ? " for this search." : "."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table w-full">
                <thead><tr><th>Product</th><th className="text-right">On Hand</th><th className="text-right">Unit Cost</th><th className="text-right">Total Value</th></tr></thead>
                <tbody>
                  {data.items.map((p) => {
                    const isOpen = !!expanded[p.product_id];
                    return (
                      <Fragment key={p.product_id}>
                        <tr className="cursor-pointer hover:bg-muted/40" onClick={() => setExpanded(x => ({ ...x, [p.product_id]: !x[p.product_id] }))} data-testid={`warehouse-row-${p.product_id}`}>
                          <td className="font-medium">
                            <span className="inline-flex items-center gap-1">
                              {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                              {p.product_name}
                            </span>
                          </td>
                          <td className="text-right">{qty(p.on_hand)}</td>
                          <td className="text-right">Rs. {fmt(p.unit_cost)}</td>
                          <td className="text-right font-semibold">Rs. {fmt(p.total_value)}</td>
                        </tr>
                        {isOpen && (
                          <tr className="bg-muted/30" data-testid={`warehouse-detail-${p.product_id}`}>
                            <td colSpan="4" className="p-0">
                              <div className="px-8 py-2">
                                <table className="w-full text-xs">
                                  <thead><tr className="text-muted-foreground text-left">
                                    <th className="py-1">Date</th><th>Source</th><th>Reference</th>
                                    <th className="text-right">Opening Qty</th><th className="text-right">Used</th>
                                    <th className="text-right">Remaining</th><th className="text-right">Unit Cost</th><th>Notes</th>
                                  </tr></thead>
                                  <tbody>
                                    {p.entries.map((e, i) => (
                                      <tr key={i} data-testid={`warehouse-lot-${p.product_id}-${i}`}>
                                        <td className="py-1">{e.date || "-"}</td>
                                        <td><Badge variant="secondary" className={`${SOURCE_COLORS[e.source_label] || "bg-gray-100"} rounded-full text-[10px]`}>{e.source_label}</Badge></td>
                                        <td>{e.reference || "-"}</td>
                                        <td className="text-right">{qty(e.opening_qty)}</td>
                                        <td className="text-right">{qty(e.used)}</td>
                                        <td className="text-right font-medium">{qty(e.remaining)}</td>
                                        <td className="text-right">Rs. {fmt(e.cost_price)}</td>
                                        <td className="text-muted-foreground">{e.notes || "-"}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="bg-muted/50 font-semibold">
                    <td className="text-right" colSpan="3">Grand Total</td>
                    <td className="text-right" data-testid="warehouse-footer-total">Rs. {fmt(data.grand_total_value)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
