import "./globals.css";
import type { Metadata } from "next";
export const metadata: Metadata = { title: "AIMi Dashboard", description: "AIMi AI wealth intelligence platform" };
export default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang="en"><body>{children}</body></html>; }
