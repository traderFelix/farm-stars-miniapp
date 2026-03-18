"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { getSessionToken } from "@/lib/auth";
import type {
    NextTaskResponse,
    TaskCheckResponse,
    TaskOpenResponse,
} from "@/lib/tasks";
import { getTelegramWebApp } from "@/lib/telegram";

type LoadState =
    | "idle"
    | "loading"
    | "success"
    | "empty"
    | "opened"
    | "completed"
    | "error";

export function TaskCard() {
    const [state, setState] = useState<LoadState>("idle");
    const [errorText, setErrorText] = useState("");
    const [successText, setSuccessText] = useState("");
    const [task, setTask] = useState<NextTaskResponse["task"]>(null);
    const [timeLeft, setTimeLeft] = useState(0);
    const [newBalance, setNewBalance] = useState<string | null>(null);

    const loadNextTask = async () => {
        const token = getSessionToken();
        if (!token) {
            setState("error");
            setErrorText("Нет session token. Сначала пройди авторизацию.");
            return;
        }

        try {
            setState("loading");
            setErrorText("");
            setSuccessText("");
            setNewBalance(null);

            const result = await apiRequest<NextTaskResponse>("/api/tasks/next", {
                method: "GET",
                token,
            });

            if (!result.task) {
                setTask(null);
                setState("empty");
                return;
            }

            setTask(result.task);
            setTimeLeft(result.task.hold_seconds);
            setState("success");

            const webApp = getTelegramWebApp();
            webApp?.HapticFeedback?.selectionChanged();
        } catch (error) {
            const message =
                error instanceof Error ? error.message : "Не удалось загрузить задание.";

            setState("error");
            setTask(null);
            setErrorText(message);

            const webApp = getTelegramWebApp();
            webApp?.HapticFeedback?.notificationOccurred("error");
        }
    };

    const openTask = async () => {
        const token = getSessionToken();
        if (!token || !task) return;

        try {
            setErrorText("");
            setSuccessText("");

            await apiRequest<TaskOpenResponse>("/api/tasks/open", {
                method: "POST",
                token,
                body: {
                    task_id: task.id,
                },
            });

            setState("opened");

            const webApp = getTelegramWebApp();
            if (webApp) {
                webApp.openTelegramLink(task.telegram_url);
            } else {
                window.open(task.telegram_url, "_blank");
            }
        } catch (error) {
            const message =
                error instanceof Error ? error.message : "Не удалось открыть задание.";
            setErrorText(message);
            setState("error");
        }
    };

    const checkTask = async () => {
        const token = getSessionToken();
        if (!token || !task) return;

        try {
            setErrorText("");
            setSuccessText("");

            const result = await apiRequest<TaskCheckResponse>("/api/tasks/check", {
                method: "POST",
                token,
                body: {
                    task_id: task.id,
                },
            });

            setSuccessText(`${result.message}. +${result.reward.toFixed(2)}⭐`);
            setNewBalance(result.new_balance.toFixed(2));
            setState("completed");

            const webApp = getTelegramWebApp();
            webApp?.HapticFeedback?.notificationOccurred("success");
        } catch (error) {
            const message =
                error instanceof Error ? error.message : "Не удалось засчитать просмотр.";

            setErrorText(message);

            const webApp = getTelegramWebApp();
            webApp?.HapticFeedback?.notificationOccurred("error");
        }
    };

    useEffect(() => {
        const token = getSessionToken();
        if (token) {
            void loadNextTask();
        }
    }, []);

    useEffect(() => {
        if (state !== "opened" || !task) return;
        if (timeLeft <= 0) return;

        const timer = setTimeout(() => {
            setTimeLeft((prev) => prev - 1);
        }, 1000);

        return () => clearTimeout(timer);
    }, [timeLeft, state, task]);

    return (
        <section className="mt-4 rounded-[28px] border border-white/10 bg-white/5 p-4 shadow-soft backdrop-blur">
            <div className="flex items-center justify-between gap-3">
                <div>
                    <div className="text-sm font-semibold">Следующее задание</div>
                    <div className="mt-1 text-xs text-white/50">
                        Шаг 6 · open/check
                    </div>
                </div>

                <button
                    type="button"
                    onClick={loadNextTask}
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

            {successText ? (
                <div className="mt-4 rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-sm text-emerald-200">
                    {successText}
                    {newBalance ? <div className="mt-1">Новый баланс: {newBalance}⭐</div> : null}
                </div>
            ) : null}

            {state === "empty" ? (
                <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-white/70">
                    Сейчас нет доступных заданий.
                </div>
            ) : null}

            {task ? (
                <div className="mt-4 space-y-3">
                    <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                        <div className="text-xs text-white/50">Тип</div>
                        <div className="mt-2 text-base font-medium">{task.type}</div>
                    </div>

                    <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                        <div className="text-xs text-white/50">Заголовок</div>
                        <div className="mt-2 text-base font-medium">{task.title}</div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                            <div className="text-xs text-white/50">Награда</div>
                            <div className="mt-2 text-xl font-semibold">
                                +{Number(task.reward).toFixed(2)}⭐
                            </div>
                        </div>

                        <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                            <div className="text-xs text-white/50">Удержание</div>
                            <div className="mt-2 text-xl font-semibold">
                                {state === "opened"
                                    ? timeLeft > 0
                                        ? `${timeLeft} сек`
                                        : "Готово"
                                    : `${task.hold_seconds} сек`}
                            </div>
                        </div>
                    </div>

                    <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
                        <div className="text-xs text-white/50">Канал</div>
                        <div className="mt-2 text-base font-medium">
                            {task.channel_name || "—"}
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={openTask}
                        disabled={state === "completed"}
                        className="w-full rounded-2xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:scale-[0.99] active:scale-[0.98] disabled:opacity-60"
                    >
                        Открыть пост
                    </button>

                    <button
                        type="button"
                        onClick={checkTask}
                        disabled={state !== "opened" || timeLeft > 0 || state === "completed"}
                        className="w-full rounded-2xl bg-emerald-400 px-4 py-3 text-sm font-semibold text-black disabled:opacity-50"
                    >
                        {state === "completed"
                            ? "Просмотр засчитан"
                            : timeLeft > 0 && state === "opened"
                                ? "Подождите..."
                                : "Засчитать просмотр"}
                    </button>
                </div>
            ) : null}
        </section>
    );
}
