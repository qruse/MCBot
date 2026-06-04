import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MCBot | Money Copy Bot",
  description: "Stock research and trading automation workspace.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
