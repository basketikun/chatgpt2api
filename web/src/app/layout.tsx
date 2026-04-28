import type { Metadata } from "next";
import { Toaster } from "sonner";

import { TopNav } from "@/components/top-nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "漱玉健康生图系统",
  description: "OpenAI-compatible image workspace",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body
        className="antialiased"
        style={{
          fontFamily:
            '"SF Pro Display","SF Pro Text","PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif',
        }}
      >
        <Toaster position="top-center" richColors />
        <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(255,255,255,0.92),_rgba(245,239,231,0.96)_42%,_rgba(240,235,227,0.99)_100%)] px-4 py-2 text-stone-900 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1440px] flex-col gap-5">
            <TopNav />
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
