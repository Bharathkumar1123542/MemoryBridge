"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

export default function CaregiverLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    setLoggingOut(true);
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  return (
    <>
      <nav className="nav">
        <Link href="/routines" className="nav-brand">MemoryBridge</Link>
        <div className="nav-links">
          <Link href="/routines/new" className={`nav-link${pathname === "/routines/new" ? " active" : ""}`}>
            + New Routine
          </Link>
          <Link href="/routines" className={`nav-link${pathname === "/routines" ? " active" : ""}`}>
            Routines
          </Link>
          <Link href="/alerts" className={`nav-link${pathname === "/alerts" ? " active" : ""}`}>
            Alerts
          </Link>
          <button
            className="btn btn-ghost"
            style={{ padding: "0.4rem 0.9rem", fontSize: "0.85rem", minHeight: "36px" }}
            onClick={handleLogout}
            disabled={loggingOut}
          >
            {loggingOut ? "..." : "Sign out"}
          </button>
        </div>
      </nav>
      <main>{children}</main>
    </>
  );
}
