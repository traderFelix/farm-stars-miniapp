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
                <div>
                    <div className="mining-kicker">Активные награды</div>
                    <h2 className="mt-1 text-xl font-semibold text-white">Активные конкурсы</h2>
                    <p className="mt-1 text-sm text-slate-300">
                        Дополнительные дропы и награды поверх основной добычи.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => void loadCampaigns({ preserveMessage: true })}
                    className="mining-ghost-button"
                    disabled={loading || claimingKey !== null}
                >
                    Обновить
                </button>
            </div>

            {loading ? (
                <div className="mining-status-note mt-4">Загружаю активные конкурсы...</div>
            ) : items.length === 0 ? (
                <div className="mining-note-card text-sm text-slate-300">
                    Сейчас нет активных конкурсов.
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

                                <button
                                    type="button"
                                    onClick={() => void handleClaim(item.campaign_key)}
                                    disabled={claimingKey !== null}
                                    className="mining-primary-button min-h-0 px-4 py-2 text-sm"
                                >
                                    {claimingKey === item.campaign_key ? "Проверяю..." : "Забрать"}
                                </button>
                            </div>
                        </div>
                    ))}
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

function formatBalance(value: number): string {
    return Number(value || 0).toFixed(2).replace(/\.00$/, "");
}
