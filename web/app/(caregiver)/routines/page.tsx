"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

interface Step { step_number: number; text?: string; simplified_text?: string; }
interface Routine {
  id: string;
  title: string;
  scheduled_time?: string;
  recurrence?: string;
  status: string;
  safety_reason?: string;
  steps?: Step[];
  created_at?: string;
}

const STATUS_LABEL: Record<string, string> = {
  pending_caregiver_approval: "Pending review",
  active: "Active",
  rejected: "Rejected",
  archived: "Archived",
};
const STATUS_CLASS: Record<string, string> = {
  pending_caregiver_approval: "badge-pending",
  active: "badge-active",
  rejected: "badge-rejected",
  archived: "badge-acknowledged",
};

export default function RoutinesPage() {
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    const res = await fetch("/api/routines");
    if (res.ok) {
      const data = await res.json();
      setRoutines(data.routines ?? []);
    }
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  function toggle(id: string) {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function approve(id: string) {
    setActionLoading(id + "-approve");
    await fetch(`/api/routines/${id}/approve`, { method: "POST" });
    await load();
    setActionLoading(null);
  }

  async function reject(id: string) {
    const reason = prompt("Reason for rejection (optional):");
    setActionLoading(id + "-reject");
    await fetch(`/api/routines/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason ?? null }),
    });
    await load();
    setActionLoading(null);
  }

  const pending = routines.filter(r => r.status === "pending_caregiver_approval");
  const others  = routines.filter(r => r.status !== "pending_caregiver_approval");

  return (
    <div className="page">
      <div className="container">
        <div className="page-header flex justify-between items-center">
          <div>
            <h1 className="page-title">Routines</h1>
            <p className="page-subtitle">Review, approve, or manage Maria&apos;s care routines.</p>
          </div>
          <Link href="/routines/new" className="btn btn-primary">+ New Routine</Link>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "3rem" }}>
            <div className="spinner" style={{ width: 36, height: 36, borderWidth: 3, margin: "0 auto" }} />
          </div>
        ) : routines.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state-icon">📋</span>
            <h3>No routines yet</h3>
            <p>Create your first routine to get started.</p>
            <Link href="/routines/new" className="btn btn-primary mt-3">Create first routine</Link>
          </div>
        ) : (
          <>
            {pending.length > 0 && (
              <section>
                <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-warning)", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span>⏳</span> Awaiting your review ({pending.length})
                </h2>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginBottom: "2rem" }}>
                  {pending.map(r => (
                    <RoutineCard key={r.id} routine={r} expanded={expanded.has(r.id)} onToggle={() => toggle(r.id)} onApprove={() => approve(r.id)} onReject={() => reject(r.id)} actionLoading={actionLoading} />
                  ))}
                </div>
              </section>
            )}
            {others.length > 0 && (
              <section>
                <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: "1rem" }}>
                  History
                </h2>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {others.map(r => (
                    <RoutineCard key={r.id} routine={r} expanded={expanded.has(r.id)} onToggle={() => toggle(r.id)} onApprove={() => approve(r.id)} onReject={() => reject(r.id)} actionLoading={actionLoading} />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function RoutineCard({ routine, expanded, onToggle, onApprove, onReject, actionLoading }: {
  routine: Routine;
  expanded: boolean;
  onToggle: () => void;
  onApprove: () => void;
  onReject: () => void;
  actionLoading: string | null;
}) {
  return (
    <div className="routine-card">
      <div className="routine-card-header" onClick={onToggle} role="button" tabIndex={0} aria-expanded={expanded} onKeyDown={e => e.key === "Enter" && onToggle()}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ marginBottom: "0.2rem" }}>{routine.title || "Untitled routine"}</h3>
          {routine.scheduled_time && (
            <p style={{ fontSize: "0.82rem", color: "var(--color-text-muted)" }}>
              {routine.scheduled_time} · {routine.recurrence}
            </p>
          )}
        </div>
        <span className={`badge ${STATUS_CLASS[routine.status] ?? "badge-acknowledged"}`}>
          {STATUS_LABEL[routine.status] ?? routine.status}
        </span>
        <span style={{ color: "var(--color-text-muted)", fontSize: "0.9rem", marginLeft: "0.5rem" }}>{expanded ? "▲" : "▼"}</span>
      </div>

      {expanded && (
        <div className="routine-card-body">
          <hr className="divider" style={{ margin: "0 0 1rem" }} />

          {routine.status === "rejected" && routine.safety_reason && (
            <div className="alert-box alert-box-error mb-2" style={{ fontSize: "0.88rem" }}>
              <span>ℹ</span> {routine.safety_reason}
            </div>
          )}

          {(routine.steps ?? []).length > 0 && (
            <ol className="routine-steps-list">
              {(routine.steps ?? []).map(s => (
                <li key={s.step_number} className="routine-step">
                  <span className="routine-step-num">{s.step_number}.</span>
                  <span className="routine-step-text">{s.simplified_text ?? s.text}</span>
                </li>
              ))}
            </ol>
          )}

          {routine.status === "pending_caregiver_approval" && (
            <div className="routine-card-actions">
              <button
                id={`approve-${routine.id}`}
                className="btn btn-success"
                onClick={onApprove}
                disabled={actionLoading === routine.id + "-approve"}
              >
                {actionLoading === routine.id + "-approve" ? <span className="spinner" /> : "✓ Approve"}
              </button>
              <button
                id={`reject-${routine.id}`}
                className="btn btn-danger"
                onClick={onReject}
                disabled={actionLoading === routine.id + "-reject"}
              >
                {actionLoading === routine.id + "-reject" ? <span className="spinner" /> : "✕ Reject"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
