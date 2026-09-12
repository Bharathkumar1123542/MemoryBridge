"use client";
import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

interface Step { step_number: number; text: string; }
interface RoutineResult {
  id: string;
  status: "pending_caregiver_approval" | "rejected";
  title?: string;
  scheduled_time?: string;
  recurrence?: string;
  steps?: Step[];
  reason?: string;
}

export default function NewRoutinePage() {
  const router = useRouter();
  const [request, setRequest] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RoutineResult | null>(null);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!request.trim()) return;
    setLoading(true);
    setResult(null);
    setError("");

    try {
      const res = await fetch("/api/routines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_request: request }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "Something went wrong. Please try again.");
        return;
      }
      setResult(data);
    } catch {
      setError("Network error. Please check your connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <div className="container-sm">
        <div className="page-header">
          <h1 className="page-title">New Routine</h1>
          <p className="page-subtitle">
            Describe the activity in plain language — the AI will plan and safety-check it.
          </p>
        </div>

        <div className="card">
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div className="form-group">
              <label className="form-label" htmlFor="routine-request">What should Maria do?</label>
              <textarea
                id="routine-request"
                className="form-textarea"
                placeholder='e.g. "Remind Maria to water the plants at 10:00 every morning."'
                value={request}
                onChange={e => setRequest(e.target.value)}
                required
                style={{ minHeight: "140px" }}
              />
            </div>
            <button
              id="submit-routine"
              type="submit"
              className="btn btn-primary btn-block btn-lg"
              disabled={loading || !request.trim()}
            >
              {loading ? <><span className="spinner" /> Planning routine…</> : "Create Routine →"}
            </button>
          </form>
        </div>

        {error && (
          <div className="alert-box alert-box-error mt-3" role="alert">
            <span>⚠</span> {error}
          </div>
        )}

        {loading && (
          <div className="card mt-3" style={{ padding: "2rem", textAlign: "center" }}>
            <div className="spinner" style={{ width: 32, height: 32, borderWidth: 3, margin: "0 auto 1rem" }} />
            <p style={{ color: "var(--color-text-secondary)" }}>
              Running safety pipeline… this takes ~10 seconds.
            </p>
          </div>
        )}

        {result && !loading && (
          <div className="mt-3">
            {result.status === "rejected" ? (
              <div className="card" style={{ borderColor: "rgba(248,113,113,0.4)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
                  <span style={{ fontSize: "1.4rem" }}>🚫</span>
                  <h3 style={{ color: "var(--color-danger)" }}>Request blocked</h3>
                </div>
                <p style={{ color: "var(--color-text-secondary)", lineHeight: 1.65 }}>
                  {result.reason}
                </p>
                <button
                  className="btn btn-ghost mt-3"
                  onClick={() => { setResult(null); setRequest(""); }}
                >
                  Try a different request
                </button>
              </div>
            ) : (
              <div className="card" style={{ borderColor: "rgba(56,189,248,0.35)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
                  <span style={{ fontSize: "1.4rem" }}>✅</span>
                  <div>
                    <h3 style={{ marginBottom: "0.15rem" }}>{result.title}</h3>
                    <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)" }}>
                      {result.scheduled_time} · {result.recurrence} · awaiting your approval
                    </p>
                  </div>
                </div>
                <ol className="routine-steps-list">
                  {(result.steps ?? []).map(s => (
                    <li key={s.step_number} className="routine-step">
                      <span className="routine-step-num">{s.step_number}.</span>
                      <span className="routine-step-text">{s.text}</span>
                    </li>
                  ))}
                </ol>
                <div style={{ display: "flex", gap: "0.75rem" }}>
                  <button
                    className="btn btn-success"
                    onClick={async () => {
                      await fetch(`/api/routines/${result.id}/approve`, { method: "POST" });
                      router.push("/routines");
                    }}
                  >
                    ✓ Approve
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={async () => {
                      await fetch(`/api/routines/${result.id}/reject`, { method: "POST" });
                      setResult(null);
                      setRequest("");
                    }}
                  >
                    Reject
                  </button>
                  <button className="btn btn-ghost" onClick={() => { setResult(null); setRequest(""); }}>
                    Start over
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
