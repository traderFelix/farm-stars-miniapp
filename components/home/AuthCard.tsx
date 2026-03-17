"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import {
    AuthResponse,
    clearSession,
    getSessionToken,
    getStoredUser,
    saveSession,
} from "@/lib/auth";
import { getTelegramInitData, getTelegramWebApp } from "@/lib/telegram";

type AuthState =
    | "idle"
    | "not_in_telegram"
    | "loading"
    | "success"
    | "error";

export function AuthCard() {
    const [state, setState] = useState<AuthState>("idle");
    const [errorText, setErrorText] = useState<string>("");
    const [sessionToken, setSessionToken] = useState<string | null>(null);
    const [userLabel, setUserLabel] = useState<string>("Не авторизован");

    useEffect(() => {
        const storedToken = getSessionToken();
        const storedUser = getStoredUser();

        if (storedToken) {
            setSessionToken(storedToken);
        }

        if (storedUser) {
            const label = storedUser.username
                ? `@${storedUser.username}`
                : `${storedUser.first_name || "User"} #${storedUser.id}`;
            setUserLabel(label);
        }
    }, []);

    const handleAuth = async () => {
        const webApp = getTelegramWebApp();
        const initData = getTelegramInitData();

        if (!webApp || !initData) {
            setState("not_in_telegram");
            setErrorText("Открой Mini App внутри Telegram.");
            return;
        }

        try {
            setState("loading");
            setErrorText("");

            const result = await apiRequest<AuthResponse>("/api/miniapp/auth", {
                method: "POST",
                body: {
                    init_data: initData,
                },
            });

            saveSession(result.session_token, result.user);
            setSessionToken(result.session_token);

            const label = result.user.username
                ? `@${result.user.username}`
                : `${result.user.first_name || "User"} #${result.user.id}`;

            setUserLabel(label);
            setState("success");

            webApp.HapticFeedback?.notificationOccurred("success");
        } catch (error) {
            const message =
                error instanceof Error ? error.message : "Не удалось авторизоваться.";

            setState("error");
            setErrorText(message);

            webApp?.HapticFeedback?.notificationOccurred("error");
        }
    };

    const handleLogout = () => {
        clearSession();
        setSessionToken(null);
        setUserLabel("Не авторизован");
        setState("idle");
        setErrorText("");
    };

    return (
        <section className="mt-4 rounded-[28px] border border-white/10 bg-white/5 p-4 shadow-soft backdrop-blur">
            <div className="text-sm font-semibold">Telegram Auth</div>

            <div className="mt-3 space-y-2 text-sm text-white/70">
                <p>
                    Статус:{" "}
                    <span className="font-medium text-white">
            {state === "success"
                ? "Авторизован"
                : state === "loading"
                    ? "Авторизация..."
                    : state === "not_in_telegram"
                        ? "Не Telegram"
                        : state === "error"
                            ? "Ошибка"
                            : "Ожидание"}
          </span>
                </p>

                <p>
                    Пользователь:{" "}
                    <span className="font-medium text-white">{userLabel}</span>
                </p>

                <p className="break-all text-xs text-white/45">
                    Session token: {sessionToken || "—"}
                </p>
            </div>

            {errorText ? (
                <div className="mt-3 rounded-2xl border border-red-400/20 bg-red-400/10 px-3 py-2 text-sm text-red-200">
                    {errorText}
                </div>
            ) : null}

            <div className="mt-4 flex gap-3">
                <button
                    type="button"
                    onClick={handleAuth}
                    disabled={state === "loading"}
                    className="rounded-2xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:scale-[0.99] active:scale-[0.98] disabled:opacity-60"
                >
                    {state === "loading" ? "Проверяем..." : "Авторизоваться"}
                </button>

                <button
                    type="button"
                    onClick={handleLogout}
                    className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-white/80"
                >
                    Сбросить
                </button>
            </div>
        </section>
    );
}
