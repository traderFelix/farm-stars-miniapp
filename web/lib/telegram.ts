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
    openLink?: (url: string) => void;
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

function isTelegramHost(hostname: string): boolean {
    return ["t.me", "telegram.me", "telegram.dog", "www.t.me"].includes(hostname.toLowerCase());
}

function normalizeTelegramUrl(url: string): string {
    const raw = (url || "").trim();
    if (!raw) {
        return raw;
    }

    if (raw.startsWith("tg://")) {
        return raw;
    }

    try {
        const parsed = new URL(raw);
        if (!isTelegramHost(parsed.hostname)) {
            return raw;
        }

        const path = parsed.pathname.replace(/\/+$/, "");
        const normalizedPath = path.replace(/^\/s\//, "/");
        const search = parsed.search || "";
        return `https://t.me${normalizedPath}${search}`;
    } catch {
        return raw;
    }
}

function openWindowFallback(url: string): boolean {
    if (typeof window === "undefined") {
        return false;
    }

    const opened = window.open(url, "_blank", "noopener,noreferrer");
    return opened !== null;
}

export function openExternalLink(url: string): boolean {
    const normalizedUrl = (url || "").trim();
    if (!normalizedUrl) {
        return false;
    }

    const webApp = getTelegramWebApp();
    if (webApp?.openLink) {
        try {
            webApp.openLink(normalizedUrl);
            return true;
        } catch {
            // Fall through to browser navigation.
        }
    }

    return openWindowFallback(normalizedUrl);
}

function scheduleTelegramLinkFallback(url: string): void {
    if (typeof window === "undefined") {
        return;
    }

    window.setTimeout(() => {
        if (document.visibilityState !== "visible") {
            return;
        }

        openWindowFallback(url);
    }, 250);
}

function isDesktopLikeTelegramPlatform(platform?: string): boolean {
    const normalized = (platform || "").toLowerCase();
    return normalized === "tdesktop" || normalized === "macos" || normalized.startsWith("web");
}

export function openTelegramLink(url: string): boolean {
    const normalizedUrl = normalizeTelegramUrl(url);
    const webApp = getTelegramWebApp();

    if (isDesktopLikeTelegramPlatform(webApp?.platform)) {
        return openWindowFallback(normalizedUrl);
    }

    if (webApp?.openTelegramLink) {
        try {
            webApp.openTelegramLink(normalizedUrl);
            scheduleTelegramLinkFallback(normalizedUrl);
            return true;
        } catch {
            // Fall through to other navigation methods.
        }
    }

    if (webApp?.openLink) {
        try {
            webApp.openLink(normalizedUrl);
            return true;
        } catch {
            // Fall through to browser navigation.
        }
    }

    return openWindowFallback(normalizedUrl);
}

export function closeTelegramMiniApp(): boolean {
    const webApp = getTelegramWebApp();
    if (webApp?.close) {
        webApp.close();
        return true;
    }

    return false;
}
