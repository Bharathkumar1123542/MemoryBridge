import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "MemoryBridge",
    template: "%s | MemoryBridge",
  },
  description:
    "AI-powered care routines for people with cognitive decline — structured, safe, and caregiver-approved.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
