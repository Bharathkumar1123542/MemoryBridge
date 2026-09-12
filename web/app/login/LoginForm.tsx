"use client";
import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

export default function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "Login failed. Please try again.");
        return;
      }
      // Redirect based on role
      if (data.role === "caregiver") {
        router.push("/routines");
      } else {
        router.push("/today");
      }
    } catch {
      setError("Network error. Please check your connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {error && (
        <div className="alert-box alert-box-error" role="alert">
          <span>⚠</span> {error}
        </div>
      )}

      <div className="form-group">
        <label className="form-label" htmlFor="email">Email address</label>
        <input
          id="email"
          type="email"
          className="form-input"
          placeholder="you@example.com"
          autoComplete="email"
          required
          value={email}
          onChange={e => setEmail(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          className="form-input"
          placeholder="••••••••"
          autoComplete="current-password"
          required
          value={password}
          onChange={e => setPassword(e.target.value)}
        />
      </div>

      <button
        id="login-submit"
        type="submit"
        className="btn btn-primary btn-block btn-lg"
        disabled={loading}
      >
        {loading ? <><span className="spinner" /> Signing in…</> : "Sign in"}
      </button>

      <p style={{ textAlign: "center", fontSize: "0.82rem", color: "var(--color-text-muted)" }}>
        Demo: use any email + password &ldquo;demo&rdquo; to explore the caregiver console.
        <br />
        Use email ending in <code style={{ color: "var(--color-accent)" }}>+today</code> to access Maria&apos;s view.
      </p>
    </form>
  );
}
