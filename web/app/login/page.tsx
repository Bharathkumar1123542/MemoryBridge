import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sign In" };

export default function LoginPage() {
  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-logo">MemoryBridge</div>
        <p className="login-tagline">Care routines, structured and safe.</p>

        <LoginForm />
      </div>
    </div>
  );
}

// Client form component inlined below
import LoginForm from "./LoginForm";
