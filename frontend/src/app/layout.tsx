import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MCBot | 전략 운용 대시보드",
  description: "Codex의 시간별 전략 연구와 모의투자 성과, 개선 근거를 확인하는 대시보드입니다.",
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
