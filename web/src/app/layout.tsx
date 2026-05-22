import type { Metadata, Viewport } from "next";
import { Toaster } from "sonner";
import "./globals.css";
import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = {
  title: "chatgpt2api — Bảng điều khiển",
  description: "Bảng điều khiển quản lý tài khoản ChatGPT, nhà cung cấp AI, tạo ảnh, sao lưu",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: "#0c0a09",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <body
        className="antialiased"
        style={{
          fontFamily:
            '"Inter","SF Pro Display","SF Pro Text","Helvetica Neue",sans-serif',
        }}
      >
        <Toaster position="top-right" richColors offset={48} />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
