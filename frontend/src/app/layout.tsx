import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: {
    default: "ClipForge — The AI-powered video clipping studio",
    template: "%s · ClipForge",
  },
  description:
    "Upload long-form videos and automatically generate high-quality short clips for YouTube Shorts, Instagram Reels and TikTok.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen font-sans">
        {children}
        <Toaster
          theme="dark"
          position="bottom-right"
          toastOptions={{
            style: {
              background: "hsl(240 8% 8%)",
              border: "1px solid hsl(240 6% 18%)",
              color: "hsl(220 14% 93%)",
            },
          }}
        />
      </body>
    </html>
  );
}
