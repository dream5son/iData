import type { Metadata } from "next";
import Link from "next/link";
import { HeaderNav } from "./header-nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "IDI · 数据源元数据治理",
  description: "实施工程师数据源接入与元数据管理",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,560;9..144,700&family=IBM+Plex+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-bg0 font-body text-ink">
        <div className="grid min-h-screen grid-rows-[auto_1fr_auto] bg-bg0">
          <header className="flex items-center gap-6 border-b border-line bg-bg0 px-4 py-3">
            <Link href="/" className="flex shrink-0 items-center gap-3 no-underline" aria-label="iData 首页">
              <img src="/logo-48.svg" alt="" width={48} height={48} className="h-12 w-12" />
              <div className="brand-lockup">
                <span className="name">iData</span>
                <p className="slogan">懂业务的<em>数据智能体</em></p>
              </div>
            </Link>
            <HeaderNav />
          </header>
          <div className="grid min-h-0 grid-cols-1 md:grid-cols-[220px_1fr]">{children}</div>
          <footer className="border-t border-line bg-bg0 px-4 py-3 text-center text-sm text-muted">
            © 2026 iData
          </footer>
        </div>
      </body>
    </html>
  );
}
