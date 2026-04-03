"use client";

import { useEffect, useState } from "react";

import { getMyReferrals, type ReferralMeResponse } from "@/lib/api";

export default function ReferralsPanel() {
    const [loading, setLoading] = useState(true);
    const [referrals, setReferrals] = useState<ReferralMeResponse | null>(null);
    const [message, setMessage] = useState("");

    async function loadReferrals(options?: { preserveMessage?: boolean }) {
        try {
            setLoading(true);
            if (!options?.preserveMessage) {
                setMessage("");
            }

            const response = await getMyReferrals();
            setReferrals(response);
        } catch (error) {
            setMessage(error instanceof Error ? error.message : "Ошибка загрузки рефералок");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void loadReferrals();
    }, []);

    async function handleCopy() {
        if (!referrals) return;

        try {
            await navigator.clipboard.writeText(referrals.invite_link);
            setMessage("Ссылка приглашения скопирована.");
        } catch {
            setMessage("Не удалось скопировать ссылку.");
        }
    }

    return (
        <div>
            <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-white/70">
                    Рефералы
                </h2>

                <button
                    type="button"
                    onClick={() => void loadReferrals({ preserveMessage: true })}
                    className="text-xs text-white/60 transition hover:text-white"
                    disabled={loading}
                >
                    Обновить
                </button>
            </div>

            {loading ? (
                <p className="mt-3 text-sm text-white/60">Загружаю реферальную ссылку...</p>
            ) : referrals ? (
                <>
                    <div className="mt-3 grid grid-cols-2 gap-3">
                        <Stat label="Приглашено" value={String(referrals.invited_count)} />
                        <Stat label="Рефбэк" value={`${formatPercent(referrals.reward_percent)}%`} />
                    </div>

                    <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/70">
                        Получай до {formatPercent(referrals.reward_percent)}% рефбека с каждого
                        вывода приглашенных пользователей.
                    </div>

                    <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                        <div className="text-xs font-semibold uppercase tracking-wide text-white/50">
                            Твоя ссылка
                        </div>
                        <div className="mt-2 break-all text-sm text-white/80">
                            {referrals.invite_link}
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={() => void handleCopy()}
                        className="mt-4 w-full rounded-xl bg-white px-4 py-3 text-sm font-medium text-black transition"
                    >
                        Скопировать ссылку
                    </button>
                </>
            ) : (
                <div className="mt-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
                    Не удалось загрузить реферальные данные
                </div>
            )}

            {message && (
                <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/80">
                    {message}
                </div>
            )}
        </div>
    );
}

function Stat({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <div className="text-xs uppercase tracking-wide text-white/50">{label}</div>
            <div className="mt-1 text-base font-semibold text-white">{value}</div>
        </div>
    );
}

function formatPercent(value: number): string {
    return Number(value || 0).toFixed(2).replace(/\.00$/, "");
}
