"use client";

declare global {
    interface Window {
        Telegram?: {
            WebApp?: TelegramWebApp;
        };
    }
}

export type TelegramWebAppUser = {
    id: number;
    first_name?: string;
    last_name?: string;
    username?: string;
    language_code?: string;
};

export type TelegramWebApp = {
    initData: string;
    initDataUnsafe?: {
        user?: TelegramWebAppUser;
        start_param?: string;
        auth_date?: number;
        hash?: string;
    };
    platform?: string;
    ready: () => void;
    expand: () => void;
    setHeaderColor?: (color: string) => void;
    setBackgroundColor?: (color: string) => void;
    showAlert: (message: string) => void;
    openTelegramLink: (url: string) => void;
    HapticFeedback?: {
        impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
        notificationOccurred: (type: "error" | "success" | "warning") => void;
        selectionChanged: () => void;
    };
};

export function getTelegramWebApp(): TelegramWebApp | null {
    if (typeof window === "undefined") return null;
    return window.Telegram?.WebApp ?? null;
}

export function initTelegramMiniApp(): TelegramWebApp | null {
    const webApp = getTelegramWebApp();
    if (!webApp) return null;

    webApp.ready();
    webApp.expand();
    webApp.setHeaderColor?.("#0b1020");
    webApp.setBackgroundColor?.("#0b1020");

    return webApp;
}

export function getTelegramInitData(): string | null {
    const webApp = getTelegramWebApp();
    if (!webApp) return null;

    return webApp.initData ?? null;
}
