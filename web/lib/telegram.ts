type TgUser = {
    id?: number;
    username?: string;
    first_name?: string;
    last_name?: string;
};

type TgWebApp = {
    initData: string;
    initDataUnsafe?: { user?: TgUser };
    platform?: string;
    ready: () => void;
    expand: () => void;
    showAlert?: (message: string) => void;
    openTelegramLink?: (url: string) => void;
    close?: () => void;
    HapticFeedback?: {
        notificationOccurred?: (type: "error" | "success" | "warning") => void;
        impactOccurred?: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
        selectionChanged?: () => void;
    };
};

declare global {
    interface Window {
        Telegram?: {
            WebApp?: TgWebApp;
        };
    }
}

export function getTelegramWebApp(): TgWebApp | undefined {
    if (typeof window === "undefined") return undefined;
    return window.Telegram?.WebApp;
}

export function initTelegramWebApp(): TgWebApp | undefined {
    const webApp = getTelegramWebApp();
    if (!webApp) return undefined;
    webApp.ready();
    webApp.expand();
    return webApp;
}

export function initTelegramMiniApp(): TgWebApp | undefined {
    return initTelegramWebApp();
}

export function getTelegramInitData(): string {
    return getTelegramWebApp()?.initData || "";
}

export function getTelegramUserUnsafe() {
    return getTelegramWebApp()?.initDataUnsafe?.user || null;
}

export function openTelegramLink(url: string): boolean {
    const webApp = getTelegramWebApp();
    if (webApp?.openTelegramLink) {
        webApp.openTelegramLink(url);
        return true;
    }

    if (typeof window !== "undefined") {
        window.location.href = url;
        return true;
    }

    return false;
}

export function closeTelegramMiniApp(): boolean {
    const webApp = getTelegramWebApp();
    if (webApp?.close) {
        webApp.close();
        return true;
    }

    return false;
}
