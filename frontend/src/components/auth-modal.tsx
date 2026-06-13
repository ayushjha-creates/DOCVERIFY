"use client";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";

export function AuthModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { login, signup } = useAuth();

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup(name, email, password);
      }
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 999
    }}>
      <div style={{
        background: "#111827", borderRadius: 16, padding: 32, width: 380,
        border: "1px solid rgba(255,255,255,0.1)", position: "relative"
      }}>
        <button onClick={onClose} style={{
          position: "absolute", top: 12, right: 16, background: "none",
          border: "none", color: "rgba(255,255,255,0.5)", cursor: "pointer", fontSize: 22
        }}>&times;</button>

        <h2 style={{ fontSize: 20, fontWeight: 700, color: "#fff", marginBottom: 20 }}>
          {mode === "login" ? "Welcome back" : "Create account"}
        </h2>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {mode === "signup" && (
            <input type="text" placeholder="Full name" value={name}
              onChange={e => setName(e.target.value)} required
              style={inputStyle} />
          )}
          <input type="email" placeholder="Email" value={email}
            onChange={e => setEmail(e.target.value)} required
            style={inputStyle} />
          <input type="password" placeholder="Password (min 6 chars)" value={password}
            onChange={e => setPassword(e.target.value)} required minLength={6}
            style={inputStyle} />

          {error && <p style={{ color: "#ef4444", fontSize: 13 }}>{error}</p>}

          <Button type="submit" disabled={submitting}
            style={{ width: "100%", padding: 12, fontSize: 15 }}>
            {submitting ? "Please wait..." : mode === "login" ? "Sign in" : "Sign up"}
          </Button>
        </form>

        <p style={{ fontSize: 13, marginTop: 16, textAlign: "center", color: "rgba(255,255,255,0.5)" }}>
          {mode === "login" ? "Don't have an account? " : "Already have an account? "}
          <button onClick={() => setMode(mode === "login" ? "signup" : "login")}
            style={{ color: "#F5A623", background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}>
            {mode === "login" ? "Sign up" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "12px 14px", borderRadius: 10, fontSize: 14,
  border: "1px solid rgba(255,255,255,0.1)", background: "#1a1a2e",
  color: "#fff", outline: "none", width: "100%"
};
