import type { Metadata, Viewport } from "next";
import Script from "next/script";
import "./globals.css";

const TELEGRAM_WEB_APP_SCRIPT = ["https://telegram.org", "js", "telegram-web-app.js"].join("/");

export const metadata: Metadata = {
    title: "Felix Farm Stars",
    description: "Мини-приложение для добычи звезд и TON",
};

export const viewport: Viewport = {
    width: "device-width",
    initialScale: 1,
    maximumScale: 1,
    viewportFit: "cover",
};

export default function RootLayout({
                                       children,
                                   }: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="ru" suppressHydrationWarning>
        <body>
        <Script src={TELEGRAM_WEB_APP_SCRIPT} strategy="beforeInteractive" />
        {children}
        </body>
        </html>
    );
}
