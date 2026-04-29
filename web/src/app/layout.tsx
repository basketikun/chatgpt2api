import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";
import { TopNav } from "@/components/top-nav";

export const metadata: Metadata = {
  title: "ChatGPT 号池管理",
  description: "ChatGPT account pool management dashboard",
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
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("theme");if(t==="dark"){document.documentElement.classList.add("dark")}else{document.documentElement.classList.remove("dark")}}catch(e){}`,
          }}
        />
        <Toaster position="top-center" richColors offset={48} />
        <main className="app-shell min-h-screen px-4 py-2 text-stone-900 dark:text-stone-100 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1440px] flex-col gap-5">
            <TopNav />
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
