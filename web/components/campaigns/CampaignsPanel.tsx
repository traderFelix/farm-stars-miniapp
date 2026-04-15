"use client";

import { useEffect, useState } from "react";

import RewardPopup from "@/components/RewardPopup";
import {
    claimCampaign,
    getActiveCampaigns,
    redeemPromo,
    toUserErrorMessage,
    type CampaignItem,
} from "@/lib/api";
import { getTelegramWebApp, openTelegramLink } from "@/lib/telegram";

type CampaignsPanelProps = {
    onBalanceChange?: (nextBalance: number) => void;
};

export default function CampaignsPanel({ onBalanceChange }: CampaignsPanelProps) {
    const [loading, setLoading] = useState(true);
    const [items, setItems] = useState<CampaignItem[]>([]);
    const [promoCode, setPromoCode] = useState("");
    const [promoSubmitting, setPromoSubmitting] = useState(false);
    const [promoError, setPromoError] = useState("");
    const [claimingKey, setClaimingKey] = useState<string | null>(null);
    const [claimError, setClaimError] = useState("");
    const [successState, setSuccessState] = useState<{
        kicker: string;
        amount: number;
        description: string;
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
                    kicker: "Награда зачислена",
                    amount: currentItem.reward_amount,
                    description: `Бонус за конкурс ${currentItem.title} уже на балансе`,
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
            setClaimError(toUserErrorMessage(error, "Не удалось забрать награду"));
            getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.("error");
        } finally {
            setClaimingKey(null);
        }
    }

    async function handlePromoRedeem() {
        const trimmedCode = promoCode.trim();
        if (!trimmedCode) {
            setPromoError("Введи промокод");
            return;
        }

        try {
            setPromoError("");
            setPromoSubmitting(true);
            const result = await redeemPromo(trimmedCode);
            if (!result.ok) {
                setPromoError(result.message || "Не удалось активировать промокод");
                getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.("error");
                return;
            }

            onBalanceChange?.(Number(result.new_balance || 0));
            setSuccessState({
                kicker: "Промокод активирован",
                amount: Number(result.reward_amount || 0),
                description: `Промокод ${result.promo_code || trimmedCode.toUpperCase()} уже зачислен на баланс`,
            });
            setPromoCode("");
            getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.("success");
        } catch (error) {
            setPromoError(toUserErrorMessage(error, "Не удалось активировать промокод"));
            getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.("error");
        } finally {
            setPromoSubmitting(false);
        }
    }

    return (
        <div>
            {successState ? (
                <RewardPopup
                    kicker={successState.kicker}
                    amountLabel={`+${formatBalance(successState.amount)} ⭐`}
                    description={successState.description}
                    onClose={() => setSuccessState(null)}
                />
            ) : null}

            <div className="flex items-center justify-between gap-3">
                <div>
                    <h2 className="mt-1 text-xl font-semibold text-white">Награды</h2>
                    <p className="mt-1 text-sm text-slate-300">
                        Активируй промокоды и забирай награды по активным розыгрышам
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

            <div className="mining-note-card mt-4">
                <div className="text-sm font-medium text-white">Активировать промокод</div>
                <div className="mt-1 text-xs text-slate-400">
                    Введи код и забери награду, если лимит активаций еще не закончился
                </div>
                <form
                    className="mt-3 flex flex-col gap-3 sm:flex-row"
                    onSubmit={(event) => {
                        event.preventDefault();
                        void handlePromoRedeem();
                    }}
                >
                    <input
                        type="text"
                        value={promoCode}
                        onChange={(event) => setPromoCode(event.target.value)}
                        placeholder="Например: WELCOME2026"
                        autoCapitalize="characters"
                        autoCorrect="off"
                        spellCheck={false}
                    />
                    <button
                        type="submit"
                        className="mining-primary-button sm:min-w-[12rem]"
                        disabled={promoSubmitting}
                    >
                        {promoSubmitting ? "Проверяю..." : "Активировать код"}
                    </button>
                </form>

                {promoError ? (
                    <div className="mining-status-note mt-3" data-tone="error">
                        {promoError}
                    </div>
                ) : null}
            </div>

            {claimError ? (
                <div className="mining-status-note mt-4" data-tone="error">
                    {claimError}
                </div>
            ) : null}

            <div className="mt-5 text-sm font-medium uppercase tracking-[0.28em] text-slate-400">
                Конкурсы
            </div>

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
