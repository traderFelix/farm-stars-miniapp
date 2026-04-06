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
                <div>
                    <div className="mining-kicker">Реферальная сеть</div>
                    <h2 className="mt-1 text-xl font-semibold text-white">Реферальная шахта</h2>
                    <p className="mt-1 text-sm text-slate-300">
                        Расти свою команду и забирай процент с их добычи.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => void loadReferrals({ preserveMessage: true })}
                    className="mining-ghost-button"
                    disabled={loading}
                >
                    Обновить
                </button>
            </div>

            {loading ? (
                <div className="mining-status-note mt-4">Загружаю реферальную ссылку...</div>
            ) : referrals ? (
                <>
                    <div className="mt-4 grid grid-cols-2 gap-3">
                        <Stat label="Приглашено" value={String(referrals.invited_count)} />
                        <Stat label="Рефбэк" value={`${formatPercent(referrals.reward_percent)}%`} />
                    </div>

                    <div className="mining-note-card text-sm text-slate-300">
                        Получай до {formatPercent(referrals.reward_percent)}% рефбека с каждого
                        вывода приглашенных пользователей.
                    </div>

                    <div className="mining-copy-card">
                        <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                            Твоя ссылка
                        </div>
                        <div className="mt-2 break-all text-sm text-slate-100">
                            {referrals.invite_link}
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={() => void handleCopy()}
                        className="mining-primary-button mt-4 w-full"
                    >
                        Скопировать ссылку
                    </button>
                </>
            ) : (
                <div className="mining-status-note mt-4" data-tone="error">
                    Не удалось загрузить реферальные данные
                </div>
            )}

            {message && (
                <div className="mining-status-note mt-4">
                    {message}
                </div>
            )}
        </div>
    );
}

function Stat({ label, value }: { label: string; value: string }) {
    return (
        <div className="mining-mini-stat" data-tone="cyan">
            <div className="mining-mini-stat__label">{label}</div>
            <div className="mt-1 text-base font-semibold text-white">{value}</div>
        </div>
    );
}

function formatPercent(value: number): string {
    return Number(value || 0).toFixed(2).replace(/\.00$/, "");
}
