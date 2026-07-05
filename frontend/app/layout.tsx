import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Advising Bot",
  description: "Simple advising assistant UI with session tracking.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>){
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
