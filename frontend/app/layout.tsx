import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "DealLens AI | Venture Intelligence", description: "Multi-agent startup due diligence." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
