import { useState, useEffect, useCallback } from "react";
import React from "react";
import API from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";
import { ShieldCheck, ChevronDown, ChevronRight, Filter } from "lucide-react";

const ACTION_STYLES = {
  Create: "bg-emerald-100 text-emerald-800 border-emerald-200",
  Edit: "bg-blue-100 text-blue-800 border-blue-200",
  Delete: "bg-red-100 text-red-800 border-red-200",
  Cancel: "bg-amber-100 text-amber-800 border-amber-200",
  Return: "bg-purple-100 text-purple-800 border-purple-200",
  Restore: "bg-slate-100 text-slate-800 border-slate-200",
};

const fmtDT = (iso) => { if (!iso) return "—"; try { return new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return iso; } };

export default function AuditTrailPage() {
  const { user } = useAuth();
  const [logs, setLogs] = useState([]);
  const [meta, setMeta] = useState({ modules: [], actions: [] });
  const [filters, setFilters] = useState({ user_email: "", module: "", action: "", date_from: "", date_to: "" });
  const [expanded, setExpanded] = useState({});
  const [loading, setLoading] = useState(true);

  const isAdmin = user?.role === "admin";

  const load = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
      const { data } = await API.get(`/audit-logs?${params.toString()}`);
      setLogs(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [filters, isAdmin]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (isAdmin) API.get("/audit-logs/meta").then((r) => setMeta(r.data)).catch(() => {});
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <Card>
        <CardContent className="p-8 text-center">
          <ShieldCheck size={32} className="mx-auto mb-2 opacity-50" />
          <div className="text-lg font-medium">Admin access required</div>
          <p className="text-sm text-muted-foreground mt-1">The audit trail is restricted to admin users.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ fontFamily: "Outfit, sans-serif" }}>Audit Trail</h1>
          <p className="text-sm text-muted-foreground mt-1">Immutable log · admin-only · no edits or deletions</p>
        </div>
        <Badge className="bg-blue-50 text-blue-700 border-blue-200 gap-1"><ShieldCheck size={12} /> Read-only</Badge>
      </div>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm flex items-center gap-2"><Filter size={14} /> Filters</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div><Label className="text-xs">User Email</Label><Input data-testid="audit-user-filter" value={filters.user_email} onChange={(e) => setFilters({ ...filters, user_email: e.target.value })} /></div>
          <div><Label className="text-xs">Module</Label>
            <Select value={filters.module || "all"} onValueChange={(v) => setFilters({ ...filters, module: v === "all" ? "" : v })}>
              <SelectTrigger data-testid="audit-module-filter"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All</SelectItem>{meta.modules.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Action</Label>
            <Select value={filters.action || "all"} onValueChange={(v) => setFilters({ ...filters, action: v === "all" ? "" : v })}>
              <SelectTrigger data-testid="audit-action-filter"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All</SelectItem>{meta.actions.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">From</Label><Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} /></div>
          <div><Label className="text-xs">To</Label><Input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} /></div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-muted-foreground">Loading…</div>
          ) : logs.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <ShieldCheck size={32} className="mx-auto mb-2 opacity-50" />
              <div>No audit entries yet</div>
              <p className="text-xs mt-1">Actions performed after go-live will appear here.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8"></TableHead>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Module</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Record</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((l) => (
                  <React.Fragment key={l.id}>
                    <TableRow data-testid={`audit-row-${l.id}`}>
                      <TableCell>
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setExpanded({ ...expanded, [l.id]: !expanded[l.id] })}>
                          {expanded[l.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </Button>
                      </TableCell>
                      <TableCell className="tabular-nums text-xs text-muted-foreground">{fmtDT(l.timestamp)}</TableCell>
                      <TableCell className="text-sm">{l.user_email || "—"}</TableCell>
                      <TableCell><Badge variant="outline" className="font-normal">{l.module}</Badge></TableCell>
                      <TableCell><Badge className={`${ACTION_STYLES[l.action] || ""} font-normal`}>{l.action}</Badge></TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{l.record_id?.slice(0, 8)}…</TableCell>
                    </TableRow>
                    {expanded[l.id] && (
                      <TableRow>
                        <TableCell colSpan={6} className="bg-muted/30 p-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-1">Previous</div>
                              <pre className="text-xs bg-background border rounded p-3 overflow-auto max-h-64">{l.previous ? JSON.stringify(l.previous, null, 2) : "—"}</pre>
                            </div>
                            <div>
                              <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-1">New</div>
                              <pre className="text-xs bg-background border rounded p-3 overflow-auto max-h-64">{l.new ? JSON.stringify(l.new, null, 2) : "—"}</pre>
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
