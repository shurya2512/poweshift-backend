import type { Metadata } from "next";
import { Space_Grotesk, Geist_Mono } from "next/font/google";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Power-Shift | Energy Deployment Intelligence",
  description: "A machine learning model trained to optimally deploy 350kW of electrical power under the strict 2026 Formula 1 regulations.",
};

import { TheInfiniteGrid } from "@/components/ui/the-infinite-grid";
import F1ScrollTracker from "@/components/F1ScrollTracker";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-black text-white relative">
        <TheInfiniteGrid>
          {children}
        </TheInfiniteGrid>
        <F1ScrollTracker />
      </body>
    </html>
  );
}
