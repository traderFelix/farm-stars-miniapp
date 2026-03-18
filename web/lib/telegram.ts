declare global {
    interface Window {
        Telegram?: {
            WebApp?: {
                initData: string;
                initDataUnsafe?: {
                    user?: {
                        id?: number;
                        username?: string;
                        first_name?: string;
                        last_name?: string;
                    };
                };
                ready: () => void;
                expand: () => void;
            };
        };
    }
}

export function initTelegramWebApp() {
    if (typeof window === "undefined") return;
    window.Telegram?.WebApp?.ready();
    window.Telegram?.WebApp?.expand();
}

export function getTelegramInitData(): string {
    if (typeof window === "undefined") return "";
    return window.Telegram?.WebApp?.initData || "";
}

export function getTelegramUserUnsafe() {
    if (typeof window === "undefined") return null;
    return window.Telegram?.WebApp?.initDataUnsafe?.user || null;
}