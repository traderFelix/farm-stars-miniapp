"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { getSessionToken } from "@/lib/auth";
import type { MeResponse } from "@/lib/me";
import { getTelegramWebApp } from "@/lib/telegram";

type LoadState = "idle" | "loading" | "success" | "error";

export function ProfileCard() {
    const [state, setState] = useState<LoadState>("idle");
    const [errorText, setErrorText] = useState("");
    const [balance, setBalance] = useState("0.00");
    const [role, setRole] = useState("—");
    const [activityIndex, setActivityIndex] = useState("0.0");
    const [userLabel, setUserLabel] = useState("—");

    const loadMe = async () => {
        const token = getSessionToken();
        if (!token) {
            setState("error");
            setErrorText("Нет session token. Сначала пройди авторизацию.");
            return;
        }

        try {
            setState("loading");
            setErrorText("");

            const result = await apiRequest<MeResponse>("/api/me", {
                method: "GET",
                token,
            });

            const u = result.user;

            setBalance(Number(u.balance || 0).toFixed(2));
            setRole(u.role || "user");
            setActivityIndex(Number(u.activity_index || 0).toFixed(1));

            const label = u.username
                ? `@${u.username}`
                : `${u.first_name || "User"} #${u.id}`;

            setUserLabel(label);
            setState("success");

            const webApp = getTelegramWebApp();
            webApp?.HapticFeedback?.notificationOccurred("success");
        } catch (error) {
            const message =
                error instanceof Error ? error.message : "Не удалось загрузить профиль.";

            setState("error");
            setErrorText(message);

            const webApp = getTelegramWebApp();
            webApp?.HapticFeedback?.notificationOccurred("error");
        }
    };

    useEffect(() => {
        const token = getSessionToken();
        if (token) {
            void loadMe();
        }
    }, []);

    return (
        <section className="mt-4 rounded-[28px] border border-white/10 bg-white/5 p-4 shadow-soft backdrop-blur">
            <div className="flex items-center justify-between gap-3">
                <div>
                    <div className="text-sm font-semibold">Профиль</div>
                    <div className="mt-1 text-xs text-white/50">
                        Главный экран Mini App
                    </div>
                </div>

                <button
                    type="button"
                    onClick={loadMe}
                    disabled={state === "loading"}
                    className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium text-white/80 disabled:opacity-60"
                >
                    {state === "loading" ? "Загрузка..." : "Обновить"}
                </button>
            </div>

            {errorText ? (
                <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-400/10 px-3 py-2 text-sm text-red-200">
                    {errorText}
                </div>
            ) : null}

            <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                    <div className="text-xs text-white/50">Баланс</div>
                    <div className="mt-2 text-2xl font-semibold">{balance}⭐</div>
                </div>

                <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                    <div className="text-xs text-white/50">Роль</div>
                    <div className="mt-2 text-base font-medium capitalize">{role}</div>
                </div>

                <div className="col-span-2 rounded-3xl border border-white/10 bg-black/20 p-4">
                    <div className="text-xs text-white/50">Пользователь</div>
                    <div className="mt-2 text-base font-medium">{userLabel}</div>
                </div>

                <div className="col-span-2 rounded-3xl border border-white/10 bg-black/20 p-4">
                    <div className="text-xs text-white/50">Индекс активности</div>
                    <div className="mt-2 text-base font-medium">{activityIndex}%</div>
                </div>
            </div>
        </section>
    );
}
