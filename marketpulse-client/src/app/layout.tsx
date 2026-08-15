import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/providers/QueryProvider";
import { LayoutShell } from "@/components/LayoutShell";
import { ThemeProvider } from "@/components/theme-provider";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jbMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jbmono" });

export const metadata: Metadata = {
  title: "MarketPulse - Real-time Market Analysis",
  description: "Professional market internals analysis with macro economic insights",
};

const noFlashScript = `
(function(){try{var t=localStorage.getItem('mp-theme');if(t!=='light'&&t!=='dark'){t='dark';}
document.documentElement.dataset.theme=t;document.documentElement.style.colorScheme=t;}catch(e){}})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: noFlashScript }} />
      </head>
      <body className={`${inter.variable} ${jbMono.variable} font-sans`}>
        <ThemeProvider>
          <QueryProvider>
            <LayoutShell>{children}</LayoutShell>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}