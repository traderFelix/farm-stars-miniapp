"use client";

import { useEffect, useState, type MouseEvent } from "react";

import {
    claimCampaign,
    getActiveCampaigns,
    type CampaignClaimResponse,
    type CampaignItem,
} from "@/lib/api";
import { openTelegramLink } from "@/lib/telegram";

type CampaignsPanelProps = {
    onBalanceChange?: (nextBalance: number) => void;
};

type NoticeTone = "error" | "success" | "warning";

type CampaignNotice = {
    title: string;
    body: string;
    tone: NoticeTone;
};

export default function CampaignsPanel({ onBalanceChange }: CampaignsPanelProps) {
    const [loading, setLoading] = useState(true);
    const [items, setItems] = useState<CampaignItem[]>([]);
    const [notice, setNotice] = useState<CampaignNotice | null>(null);
    const [claimingKey, setClaimingKey] = useState<string | null>(null);

    async function loadCampaigns(options?: { preserveNotice?: boolean }) {
        try {
            setLoading(true);
            if (!options?.preserveNotice) {
                setNotice(null);
            }

            const response = await getActiveCampaigns();
            setItems(response.items || []);
        } catch (error) {
            setNotice({
                tone: "error",
                title: "Не удалось загрузить конкурсы",
                body: error instanceof Error ? error.message : "Попробуй еще раз позже",
            });
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void loadCampaigns();
    }, []);

    async function handleClaim(campaignKey: string) {
        const currentItem = items.find((item) => item.campaign_key === campaignKey);

        try {
            setClaimingKey(campaignKey);
            setNotice(null);

            const result = await claimCampaign(campaignKey);
            setNotice(buildClaimNotice(result, currentItem));

            if (result.ok) {
                onBalanceChange?.(Number(result.new_balance || 0));
                setItems((prev) => prev.filter((item) => item.campaign_key !== campaignKey));
            }
        } catch (error) {
            setNotice({
                tone: "error",
                title: "Не удалось получить награду",
                body: error instanceof Error ? error.message : "Попробуй еще раз позже",
            });
        } finally {
            setClaimingKey(null);
        }
    }

    function handlePostLinkClick(event: MouseEvent<HTMLAnchorElement>, postUrl: string) {
        event.preventDefault();

        if (!openTelegramLink(postUrl)) {
            setNotice({
                tone: "warning",
                title: "Не удалось открыть пост",
                body: "Попробуй открыть ссылку еще раз",
            });
        }
    }

    return (
        <div>
            <div className="flex items-center justify-between gap-3">
                <div>
                    <h2 className="mt-1 text-xl font-semibold text-white">Активные конкурсы</h2>
                    <p className="mt-1 text-sm text-slate-300">
                        Дополнительные дропы и награды поверх основной добычи
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => void loadCampaigns({ preserveNotice: true })}
                    className="mining-ghost-button"
                    disabled={loading || claimingKey !== null}
                >
                    Обновить
                </button>
            </div>

            {notice && (
                <div className="mining-status-note mt-4" data-tone={notice.tone}>
                    <div className="text-sm font-semibold text-white">{notice.title}</div>
                    <div className="mt-1 text-sm">{notice.body}</div>
                </div>
            )}

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

                                <button
                                    type="button"
                                    onClick={() => void handleClaim(item.campaign_key)}
                                    disabled={claimingKey !== null}
                                    className="mining-primary-button min-h-0 px-4 py-2 text-sm"
                                >
                                    {claimingKey === item.campaign_key ? "Проверяю..." : "Забрать"}
                                </button>
                            </div>

                            <div className="mining-note-card mt-3 text-sm text-slate-300">
                                <div className="font-medium text-white">Пост с розыгрышем был тут</div>
                                {item.post_url ? (
                                    <a
                                        href={item.post_url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="mining-link mt-1 inline-flex"
                                        onClick={(event) => handlePostLinkClick(event, item.post_url!)}
                                    >
                                        Открыть пост
                                    </a>
                                ) : (
                                    <div className="mt-1 text-slate-400">Ссылка появится позже</div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function buildClaimNotice(
    result: CampaignClaimResponse,
    item?: CampaignItem,
): CampaignNotice {
    if (result.ok) {
        return {
            tone: "success",
            title: "Награда зачислена",
            body: item
                ? `${formatBalance(item.reward_amount)} ⭐ уже на балансе за конкурс «${item.title}»`
                : sanitizeMessage(result.message),
        };
    }

    switch (result.code) {
        case "not_winner":
            return {
                tone: "error",
                title: "Награда недоступна",
                body: "В этом конкурсе тебя нет среди победителей",
            };
        case "inactive":
            return {
                tone: "warning",
                title: "Конкурс уже закрыт",
                body: "Этот розыгрыш сейчас неактивен",
            };
        case "already_claimed":
            return {
                tone: "warning",
                title: "Награда уже получена",
                body: "Бонус по этому конкурсу уже был зачислен раньше",
            };
        case "rate_limited":
        case "too_many_failures":
            return {
                tone: "warning",
                title: "Попробуй чуть позже",
                body: sanitizeMessage(result.message),
            };
        default:
            return {
                tone: "error",
                title: "Не удалось получить награду",
                body: sanitizeMessage(result.message),
            };
    }
}

function sanitizeMessage(value: string): string {
    return (value || "").trim() || "Попробуй еще раз позже";
}

function formatBalance(value: number): string {
    return Number(value || 0).toFixed(2).replace(/\.00$/, "");
}
