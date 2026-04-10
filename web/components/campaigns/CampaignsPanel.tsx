"use client";

import { useEffect, useState } from "react";

import {
    claimCampaign,
    getActiveCampaigns,
    type CampaignItem,
} from "@/lib/api";
import { getTelegramWebApp, openTelegramLink } from "@/lib/telegram";

type CampaignsPanelProps = {
    onBalanceChange?: (nextBalance: number) => void;
};

export default function CampaignsPanel({ onBalanceChange }: CampaignsPanelProps) {
    const [loading, setLoading] = useState(true);
    const [items, setItems] = useState<CampaignItem[]>([]);
    const [claimingKey, setClaimingKey] = useState<string | null>(null);
    const [claimError, setClaimError] = useState("");
    const [successState, setSuccessState] = useState<{
        title: string;
        amount: number;
    } | null>(null);

    async function loadCampaigns() {
        try {
            setLoading(true);
            const response = await getActiveCampaigns();
            setItems(response.items || []);
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void loadCampaigns();
    }, []);

    async function handleClaim(campaignKey: string) {
        const currentItem = items.find((item) => item.campaign_key === campaignKey);
        if (!currentItem?.is_winner || currentItem.already_claimed) {
            return;
        }

        try {
            setClaimError("");
            setClaimingKey(campaignKey);
            const result = await claimCampaign(campaignKey);

            if (result.ok) {
                onBalanceChange?.(Number(result.new_balance || 0));
                setSuccessState({
                    title: currentItem.title,
                    amount: currentItem.reward_amount,
                });
                getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.("success");
                setItems((prev) =>
                    prev.map((item) =>
                        item.campaign_key === campaignKey
                            ? {
                                ...item,
                                already_claimed: true,
                              }
                            : item
                    )
                );
            } else {
                setClaimError(result.message || "Не удалось забрать награду");
                getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.("error");
            }
        } catch (error) {
            setClaimError(error instanceof Error ? error.message : "Не удалось забрать награду");
            getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.("error");
        } finally {
            setClaimingKey(null);
        }
    }

    return (
        <div>
            {successState ? (
                <div className="mining-popup-backdrop" onClick={() => setSuccessState(null)}>
                    <div
                        className="mining-popup-card mining-popup-card--success"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="mining-popup-card__kicker">Награда зачислена</div>
                        <div className="mining-popup-card__title">
                            +{formatBalance(successState.amount)} ⭐
                        </div>
                        <div className="mining-popup-card__text">
                            Бонус за конкурс {successState.title} уже на балансе
                        </div>
                        <button
                            type="button"
                            className="mining-primary-button mt-4 w-full"
                            onClick={() => setSuccessState(null)}
                        >
                            Отлично
                        </button>
                    </div>
                </div>
            ) : null}

            <div className="flex items-center justify-between gap-3">
                <div>
                    <h2 className="mt-1 text-xl font-semibold text-white">Активные конкурсы</h2>
                    <p className="mt-1 text-sm text-slate-300">
                        Дополнительные дропы и награды поверх основной добычи
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => void loadCampaigns()}
                    className="mining-ghost-button"
                    disabled={loading || claimingKey !== null}
                >
                    Обновить
                </button>
            </div>

            {claimError ? (
                <div className="mining-status-note mt-4" data-tone="error">
                    {claimError}
                </div>
            ) : null}

            {loading ? (
                <div className="mining-status-note mt-4">Загружаю активные конкурсы...</div>
            ) : items.length === 0 ? (
                <div className="mining-note-card mt-4 text-sm text-slate-300">
                    Сейчас нет активных конкурсов
                </div>
            ) : (
                <div className="mt-4 flex flex-col gap-3">
                    {items.map((item) => (
                        <div
                            key={item.campaign_key}
                            className="mining-list-card"
                        >
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <div className="text-sm font-medium text-white">{item.title}</div>
                                    <div className="mt-1 text-xs text-slate-400">
                                        Награда: {formatBalance(item.reward_amount)} ⭐
                                    </div>
                                </div>

                                {item.post_button_url ? (
                                    <button
                                        type="button"
                                        className="mining-inline-button mining-inline-button--corner"
                                        onClick={() => {
                                            void openTelegramLink(item.post_button_url!);
                                        }}
                                    >
                                        {item.post_button_label || "Пост с розыгрышем"}
                                    </button>
                                ) : null}
                            </div>

                            <button
                                type="button"
                                onClick={() => void handleClaim(item.campaign_key)}
                                disabled={claimingKey !== null || !item.is_winner || item.already_claimed}
                                className="mining-primary-button mt-4 w-full"
                            >
                                {claimingKey === item.campaign_key ? "Проверяю..." : "Забрать награду"}
                            </button>

                            {item.already_claimed ? (
                                <div className="mt-3 text-sm font-medium text-rose-300">
                                    Награда уже получена
                                </div>
                            ) : !item.is_winner ? (
                                <div className="mt-3 text-sm font-medium text-rose-300">
                                    Тебя нет в списке победителей
                                </div>
                            ) : null}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function formatBalance(value: number): string {
    return Number(value || 0).toFixed(2).replace(/\.00$/, "");
}
