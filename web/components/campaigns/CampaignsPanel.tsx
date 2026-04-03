"use client";

import { useEffect, useState } from "react";

import {
    claimCampaign,
    getActiveCampaigns,
    type CampaignItem,
} from "@/lib/api";

type CampaignsPanelProps = {
    onBalanceChange?: (nextBalance: number) => void;
};

export default function CampaignsPanel({ onBalanceChange }: CampaignsPanelProps) {
    const [loading, setLoading] = useState(true);
    const [items, setItems] = useState<CampaignItem[]>([]);
    const [message, setMessage] = useState("");
    const [claimingKey, setClaimingKey] = useState<string | null>(null);

    async function loadCampaigns(options?: { preserveMessage?: boolean }) {
        try {
            setLoading(true);
            if (!options?.preserveMessage) {
                setMessage("");
            }

            const response = await getActiveCampaigns();
            setItems(response.items || []);
        } catch (error) {
            setMessage(error instanceof Error ? error.message : "Ошибка загрузки конкурсов");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void loadCampaigns();
    }, []);

    async function handleClaim(campaignKey: string) {
        try {
            setClaimingKey(campaignKey);
            setMessage("");

            const result = await claimCampaign(campaignKey);
            setMessage(result.message);

            if (result.ok) {
                onBalanceChange?.(Number(result.new_balance || 0));
                setItems((prev) => prev.filter((item) => item.campaign_key !== campaignKey));
            }
        } catch (error) {
            setMessage(error instanceof Error ? error.message : "Ошибка получения награды");
        } finally {
            setClaimingKey(null);
        }
    }

    return (
        <div>
            <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-white/70">
                    Конкурсы
                </h2>

                <button
                    type="button"
                    onClick={() => void loadCampaigns({ preserveMessage: true })}
                    className="text-xs text-white/60 transition hover:text-white"
                    disabled={loading || claimingKey !== null}
                >
                    Обновить
                </button>
            </div>

            {loading ? (
                <p className="mt-3 text-sm text-white/60">Загружаю активные конкурсы...</p>
            ) : items.length === 0 ? (
                <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/60">
                    Сейчас нет активных конкурсов.
                </div>
            ) : (
                <div className="mt-3 flex flex-col gap-3">
                    {items.map((item) => (
                        <div
                            key={item.campaign_key}
                            className="rounded-xl border border-white/10 bg-black/20 p-3"
                        >
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <div className="text-sm font-medium text-white">{item.title}</div>
                                    <div className="mt-1 text-xs text-white/50">
                                        Награда: {formatBalance(item.reward_amount)} ⭐
                                    </div>
                                </div>

                                <button
                                    type="button"
                                    onClick={() => void handleClaim(item.campaign_key)}
                                    disabled={claimingKey !== null}
                                    className="rounded-xl bg-white px-3 py-2 text-xs font-medium text-black transition disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    {claimingKey === item.campaign_key ? "Проверяю..." : "Забрать"}
                                </button>
                            </div>
                        </div>
                    ))}
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

function formatBalance(value: number): string {
    return Number(value || 0).toFixed(2).replace(/\.00$/, "");
}
