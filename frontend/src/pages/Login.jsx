import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Boxes, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";

export default function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await signIn(email, password);
      navigate("/");
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* left brand panel */}
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-[#0d0d0f] border-r border-[#27272A] p-12 relative overflow-hidden">
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{ backgroundImage: "url('https://images.unsplash.com/photo-1566410824233-a8011929225c?crop=entropy&cs=srgb&fm=jpg&q=85')", backgroundSize: "cover" }}
        />
        <div className="flex items-center gap-3 relative z-10">
          <div className="h-9 w-9 rounded-sm bg-orange-500 flex items-center justify-center">
            <Boxes className="h-5 w-5 text-black" strokeWidth={2} />
          </div>
          <span className="font-head font-bold text-white text-lg">InfraForge</span>
        </div>
        <div className="relative z-10">
          <h1 className="font-head font-bold text-4xl text-white leading-tight">
            The source of truth for<br />your AWS infrastructure.
          </h1>
          <p className="text-zinc-500 mt-4 max-w-md">
            Centralize hosts, DNS, EC2 metadata — then generate reviewable Terraform in one click.
          </p>
        </div>
        <div className="font-mono text-xs text-zinc-600 relative z-10">// internal DevOps portal</div>
      </div>

      {/* right form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-[#09090B]">
        <form onSubmit={submit} className="w-full max-w-sm space-y-6">
          <div className="lg:hidden flex items-center gap-3 mb-2">
            <div className="h-9 w-9 rounded-sm bg-orange-500 flex items-center justify-center">
              <Boxes className="h-5 w-5 text-black" strokeWidth={2} />
            </div>
            <span className="font-head font-bold text-white text-lg">InfraForge</span>
          </div>
          <div>
            <h2 className="font-head font-semibold text-2xl text-white">Team sign in</h2>
            <p className="text-sm text-zinc-500 mt-1">Access the infrastructure portal</p>
          </div>

          {error && (
            <div data-testid="login-error" className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-sm px-3 py-2">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs text-zinc-400">Email</Label>
            <Input data-testid="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
              className="bg-[#18181B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2" placeholder="you@company.com" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-zinc-400">Password</Label>
            <Input data-testid="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              className="bg-[#18181B] border-[#27272A] text-white font-mono text-sm focus-visible:ring-orange-500/50 focus-visible:ring-2" placeholder="••••••••" />
          </div>
          <Button data-testid="login-submit" type="submit" disabled={busy}
            className="w-full bg-orange-500 hover:bg-orange-600 text-white rounded-sm h-11 gap-2">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-[11px] text-zinc-600 font-mono text-center">
            Accounts are created by an admin in Team Settings.
          </p>
        </form>
      </div>
    </div>
  );
}
