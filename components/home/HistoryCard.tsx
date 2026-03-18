"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { getSessionToken } from "@/lib/auth";
import type { HistoryResponse } from "@/lib/tasks";

type LoadState = "idle" | "loading" | "success" | "error";

export function HistoryCard() {
    const [state, setState] = useState<LoadState>("idle");
    const [errorText, setErrorText] = useState("");
    const [items, setItems] = useState<HistoryResponse["items"]>([]);

    const loadHistory = async () => {
        const token = getSessionToken();
        if (!token) {
            setState("error");
            setErrorText("Сначала пройди авторизацию.");
            return;
        }

        try {
            setState("loading");
            setErrorText("");

            const result = await apiRequest<HistoryResponse>("/api/history", {
                method: "GET",
                token,
            });

            setItems(result.items);
            setState("success");
        } catch (error) {
            const message =
                error instanceof Error ? error.message : "Не удалось загрузить историю.";
            setErrorText(message);
            setState("error");
        }
    };

    useEffect(() => {
        const token = getSessionToken();
        if (token) {
            void loadHistory();
        }
    }, []);

    return (
        <section className="mt-4 rounded-[28px] border border-white/10 bg-white/5 p-4 shadow-soft backdrop-blur">
            <div className="flex items-center justify-between gap-3">
                <div>
                    <div className="text-sm font-semibold">История</div>
                    <div className="mt-1 text-xs text-white/50">
                        Последние выполненные задания
                    </div>
                </div>

                <button
                    type="button"
                    onClick={loadHistory}
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

            {!items.length && state === "success" ? (
                <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-white/70">
                    История пока пустая.
                </div>
            ) : null}

            {items.length ? (
                <div className="mt-4 space-y-3">
                    {items.map((item) => (
                        <div
                            key={`${item.task_id}-${item.completed_at}`}
                            className="rounded-3xl border border-white/10 bg-black/20 p-4"
                        >
                            <div className="text-sm font-medium">{item.title}</div>
                            <div className="mt-2 flex items-center justify-between text-xs text-white/55">
                                <span>+{item.reward.toFixed(2)}⭐</span>
                                <span>
                  {new Date(item.completed_at * 1000).toLocaleString()}
                </span>
                            </div>
                        </div>
                    ))}
                </div>
            ) : null}
        </section>
    );
}