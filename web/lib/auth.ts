"use client";

export type MiniAppUser = {
    id: number;
    game_nickname?: string | null;
};

export type AuthResponse = {
    ok: true;
    session_token: string;
    user: MiniAppUser;
};

const SESSION_STORAGE_KEY = "ffs_session_token";
const USER_STORAGE_KEY = "ffs_user";

export function saveSession(token: string, user: MiniAppUser) {
    if (typeof window === "undefined") return;
    localStorage.setItem(SESSION_STORAGE_KEY, token);
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
}

export function getSessionToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(SESSION_STORAGE_KEY);
}

export function getStoredUser(): MiniAppUser | null {
    if (typeof window === "undefined") return null;

    const raw = localStorage.getItem(USER_STORAGE_KEY);
    if (!raw) return null;

    try {
        return JSON.parse(raw) as MiniAppUser;
    } catch {
        return null;
    }
}

export function clearSession() {
    if (typeof window === "undefined") return;
    localStorage.removeItem(SESSION_STORAGE_KEY);
    localStorage.removeItem(USER_STORAGE_KEY);
}
