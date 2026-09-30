import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FlowForge",
  description: "Design, approve, and track your organization's business workflows.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
