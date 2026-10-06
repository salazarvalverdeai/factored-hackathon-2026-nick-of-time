import type { Metadata } from "next";
import { JetBrains_Mono, Sora } from "next/font/google";
import "./globals.css";
import { MotionReady } from "@/components/motion/motion-group";
import { ThemeProvider } from "@/components/theme-provider";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { MOTION_HEAD_SCRIPT } from "@/lib/motion";

const sora = Sora({
  variable: "--font-sora",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  // "/" shows the default; every other route sets its own title in its segment: "<Page> · Nick of Time".
  title: { default: "Nick of Time", template: "%s · Nick of Time" },
  description: "Verified action. Before the deadline.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${sora.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <head>
        {/* Motion kit (components/motion/README.md): before the first paint, so a mark never shows and then hides. */}
        <script dangerouslySetInnerHTML={{ __html: MOTION_HEAD_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">
        <MotionReady />
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
          <SiteHeader />
          {children}
          <SiteFooter />
        </ThemeProvider>
      </body>
    </html>
  );
}
