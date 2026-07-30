import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Advising Bot",
  description: "Simple advising assistant UI with thread tracking.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>){
  return (
    <html lang="en">
      {/* suppressHydrationWarning: browser extensions (e.g. Grammarly) inject
          attributes onto <body> before hydration, causing a false mismatch. */}
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
