import { useEffect, useState } from "react";
import API from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { toast } from "sonner";
import { UserPlus, KeyRound, Trash2, ShieldCheck, User as UserIcon } from "lucide-react";

export default function UsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "user" });
  const [creating, setCreating] = useState(false);

  const [resetTarget, setResetTarget] = useState(null);
  const [newPassword, setNewPassword] = useState("");
  const [resetting, setResetting] = useState(false);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const { data } = await API.get("/users");
      setUsers(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  if (me?.role !== "admin") {
    return (
      <div className="text-center py-12 text-muted-foreground" data-testid="users-no-access">
        Admin access required.
      </div>
    );
  }

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      await API.post("/users", {
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
      });
      toast.success(`User ${form.email} created`);
      setForm({ name: "", email: "", password: "", role: "user" });
      setCreateOpen(false);
      fetchUsers();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create user");
    } finally {
      setCreating(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setResetting(true);
    try {
      await API.post(`/users/${resetTarget.id}/reset-password`, { new_password: newPassword });
      toast.success(`Password reset for ${resetTarget.email}`);
      setResetTarget(null);
      setNewPassword("");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to reset password");
    } finally {
      setResetting(false);
    }
  };

  const handleDelete = async (u) => {
    if (!window.confirm(`Delete user ${u.email}? This cannot be undone.`)) return;
    try {
      await API.delete(`/users/${u.id}`);
      toast.success(`User ${u.email} deleted`);
      fetchUsers();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to delete user");
    }
  };

  return (
    <div className="space-y-6" data-testid="users-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ fontFamily: 'Outfit, sans-serif' }}>Users</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage who can access the system. Only admins can add or remove users.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} className="bg-[#0F172A] hover:bg-[#1E293B] gap-2" data-testid="add-user-button">
          <UserPlus size={16} /> Add User
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">All users ({users.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="py-8 text-center text-muted-foreground">Loading...</div>
          ) : users.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">No users yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">Email</th>
                    <th className="py-2 pr-4 font-medium">Role</th>
                    <th className="py-2 pr-4 font-medium">Created</th>
                    <th className="py-2 pr-4 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const isMe = u.id === me.id;
                    return (
                      <tr key={u.id} className="border-b last:border-0" data-testid={`user-row-${u.email}`}>
                        <td className="py-3 pr-4 font-medium">{u.name || "—"}</td>
                        <td className="py-3 pr-4">{u.email}</td>
                        <td className="py-3 pr-4">
                          <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-sm ${u.role === "admin" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-700"}`}>
                            {u.role === "admin" ? <ShieldCheck size={12} /> : <UserIcon size={12} />}
                            {u.role}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-muted-foreground text-xs">
                          {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                        </td>
                        <td className="py-3 pr-4 text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => { setResetTarget(u); setNewPassword(""); }}
                            data-testid={`reset-password-${u.email}`}
                            className="gap-1"
                          >
                            <KeyRound size={14} /> Reset password
                          </Button>
                          {!isMe && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(u)}
                              data-testid={`delete-user-${u.email}`}
                              className="gap-1 text-destructive hover:text-destructive"
                            >
                              <Trash2 size={14} /> Delete
                            </Button>
                          )}
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

      {/* CREATE USER DIALOG */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-[440px]" data-testid="create-user-dialog">
          <DialogHeader>
            <DialogTitle>Add a new user</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wider font-semibold">Name</Label>
              <Input
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="Full name"
                required
                data-testid="new-user-name"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wider font-semibold">Email</Label>
              <Input
                type="email"
                value={form.email}
                onChange={e => setForm({ ...form, email: e.target.value })}
                placeholder="user@example.com"
                required
                data-testid="new-user-email"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wider font-semibold">Initial Password</Label>
              <Input
                type="text"
                value={form.password}
                onChange={e => setForm({ ...form, password: e.target.value })}
                placeholder="Min 6 characters"
                minLength={6}
                required
                data-testid="new-user-password"
              />
              <p className="text-xs text-muted-foreground">Share this with the user. They can change it later by asking you to reset.</p>
            </div>
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wider font-semibold">Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger data-testid="new-user-role"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User (regular access)</SelectItem>
                  <SelectItem value="admin">Admin (can manage users)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DialogFooter className="gap-2 sm:gap-0">
              <Button type="button" variant="ghost" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button type="submit" className="bg-[#0F172A] hover:bg-[#1E293B]" disabled={creating} data-testid="submit-new-user">
                {creating ? "Creating..." : "Create User"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* RESET PASSWORD DIALOG */}
      <Dialog open={!!resetTarget} onOpenChange={(o) => !o && setResetTarget(null)}>
        <DialogContent className="sm:max-w-[440px]" data-testid="reset-password-dialog">
          <DialogHeader>
            <DialogTitle>Reset password</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleResetPassword} className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Setting a new password for <strong>{resetTarget?.email}</strong>. They will need to use this password the next time they sign in.
            </p>
            <div className="space-y-2">
              <Label className="text-xs uppercase tracking-wider font-semibold">New password</Label>
              <Input
                type="text"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                placeholder="Min 6 characters"
                minLength={6}
                required
                data-testid="reset-new-password-input"
              />
            </div>
            <DialogFooter className="gap-2 sm:gap-0">
              <Button type="button" variant="ghost" onClick={() => setResetTarget(null)}>Cancel</Button>
              <Button type="submit" className="bg-[#0F172A] hover:bg-[#1E293B]" disabled={resetting} data-testid="submit-reset-password">
                {resetting ? "Resetting..." : "Reset Password"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
