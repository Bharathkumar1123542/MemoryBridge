"use client";
import { useEffect, useState } from "react";

interface Alert {
  id: string;
  category: string;
  message: string;
  source_note?: string;
  status: "open" | "acknowledged" | "resolved";
  created_at?: string;
}

function formatTime(iso?: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch { return iso; }
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [ackLoading, setAckLoading] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    const res = await fetch("/api/alerts");
    if (res.ok) {
      const data = await res.json();
      setAlerts(data.alerts ?? []);
    }
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function acknowledge(id: string) {
    setAckLoading(id);
    await fetch(`/api/alerts/${id}/acknowledge`, { method: "POST" });
    await load();
    setAckLoading(null);
  }

  const open = alerts.filter(a => a.status === "open");
  const acknowledged = alerts.filter(a => a.status !== "open");

  return (
    <div className="page">
      <div className="container">
        <div className="page-header">
          <h1 className="page-title">Help Alerts</h1>
          <p className="page-subtitle">
            Alerts from Maria&apos;s &ldquo;Help me&rdquo; button — newest first.
          </p>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "3rem" }}>
            <div className="spinner" style={{ width: 36, height: 36, borderWidth: 3, margin: "0 auto" }} />
          </div>
        ) : alerts.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state-icon">🔔</span>
            <h3>No alerts yet</h3>
            <p>When Maria taps &ldquo;Help me&rdquo; you&apos;ll see it here.</p>
          </div>
        ) : (
          <>
            {open.length > 0 && (
              <section>
                <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-warning)", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span>🔔</span> Open ({open.length})
                </h2>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem", marginBottom: "2rem" }}>
                  {open.map(a => (
                    <AlertItem key={a.id} alert={a} onAck={() => acknowledge(a.id)} ackLoading={ackLoading === a.id} />
                  ))}
                </div>
              </section>
            )}
            {acknowledged.length > 0 && (
              <section>
                <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-text-muted)", marginBottom: "1rem" }}>
                  Acknowledged
                </h2>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
                  {acknowledged.map(a => (
                    <AlertItem key={a.id} alert={a} onAck={() => acknowledge(a.id)} ackLoading={ackLoading === a.id} />
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

function AlertItem({ alert, onAck, ackLoading }: { alert: Alert; onAck: () => void; ackLoading: boolean }) {
  return (
    <div className={`alert-item ${alert.status}`}>
      <div className="alert-item-body">
        <div className="alert-item-category">{alert.category.replace(/_/g, " ")}</div>
        <div className="alert-item-message">{alert.message}</div>
        {alert.source_note && (
          <div style={{ fontSize: "0.82rem", color: "var(--color-text-muted)", marginTop: "0.35rem" }}>
            Note: &ldquo;{alert.source_note}&rdquo;
          </div>
        )}
        <div className="alert-item-time">{formatTime(alert.created_at)}</div>
      </div>
      {alert.status === "open" && (
        <button
          id={`ack-${alert.id}`}
          className="btn btn-ghost"
          style={{ flexShrink: 0, fontSize: "0.82rem", padding: "0.4rem 0.8rem", minHeight: "36px" }}
          onClick={onAck}
          disabled={ackLoading}
        >
          {ackLoading ? <span className="spinner" /> : "Acknowledge"}
        </button>
      )}
    </div>
  );
}
