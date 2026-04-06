"use client";

import { useEffect, useState } from "react";
import {
    createWithdrawal,
    getMyWithdrawals,
    getWithdrawalEligibility,
    type WithdrawalEligibilityResponse,
    type WithdrawalItem,
    type WithdrawalMethod,
} from "@/lib/api";

export default function WithdrawalPanel() {
    const [loading, setLoading] = useState(true);
    const [eligibility, setEligibility] =
        useState<WithdrawalEligibilityResponse | null>(null);
    const [withdrawals, setWithdrawals] = useState<WithdrawalItem[]>([]);

    const [method, setMethod] = useState<WithdrawalMethod>("stars");
    const [amount, setAmount] = useState<string>("");
    const [wallet, setWallet] = useState<string>("");

    const [submitting, setSubmitting] = useState(false);
    const [message, setMessage] = useState<string>("");

    async function loadPanelData(options?: { preserveMessage?: boolean }) {
        try {
            setLoading(true);

            if (!options?.preserveMessage) {
                setMessage("");
            }

            const [eligibilityData, myWithdrawalsData] = await Promise.all([
                getWithdrawalEligibility(),
                getMyWithdrawals(10),
            ]);

            setEligibility(eligibilityData);
            setWithdrawals(myWithdrawalsData.items || []);
        } catch (e) {
            setMessage(e instanceof Error ? e.message : "Ошибка загрузки вывода");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void loadPanelData();
    }, []);

    async function handleSubmit() {
        if (!eligibility?.can_withdraw) return;

        const amountNum = Number(amount);

        if (!amount || Number.isNaN(amountNum) || amountNum <= 0) {
            setMessage("Введите корректную сумму вывода");
            return;
        }

        if (method === "ton" && !wallet.trim()) {
            setMessage("Введите TON-кошелек");
            return;
        }

        try {
            setSubmitting(true);
            setMessage("");

            const res = await createWithdrawal({
                method,
                amount: amountNum,
                wallet: method === "ton" ? wallet.trim() : null,
            });

            setMessage(res.message);

            await loadPanelData({ preserveMessage: true });

            setAmount("");
            setWallet("");
        } catch (e) {
            setMessage(e instanceof Error ? e.message : "Ошибка создания заявки");
        } finally {
            setSubmitting(false);
        }
    }

    if (loading) {
        return <div className="text-sm text-white/60">Загрузка вывода...</div>;
    }

    if (!eligibility) {
        return <div className="text-sm text-red-200">Не удалось загрузить вывод</div>;
    }

    return (
        <div>
            <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-white/70">
                    Вывод
                </h2>

                <button
                    type="button"
                    onClick={() => void loadPanelData({ preserveMessage: true })}
                    className="text-xs text-white/60 transition hover:text-white"
                    disabled={loading || submitting}
                >
                    Обновить
                </button>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-3">
                <Stat label="Баланс" value={`${formatBalance(eligibility.available_balance)} ⭐`} />
                <Stat
                    label="Статус"
                    value={eligibility.can_withdraw ? "Доступен" : "Недоступен"}
                />
                <Stat
                    label="Мин. вывод"
                    value={`${formatBalance(eligibility.min_withdraw)} ⭐`}
                />
                <Stat
                    label="Из заданий"
                    value={`${formatBalance(eligibility.task_earnings_percent)}%`}
                />
            </div>

            <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/80">
                {eligibility.message}
            </div>

            <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-white/50">
                    Условия вывода
                </div>

                <div className="mt-2 grid gap-1 text-sm text-white/70">
                    <div>• Минимальная сумма: {formatBalance(eligibility.min_withdraw)} ⭐</div>
                    <div>
                        • Индекс Активности не меннее {formatBalance(eligibility.min_task_percent)}%
                    </div>
                    <div>
                        • Курс обмена в TON определяется по рынку{" "}
                        <a
                            href={eligibility.policy.rate_source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-white underline decoration-white/30 underline-offset-2"
                        >
                            {eligibility.policy.rate_source_name}
                        </a>
                    </div>
                    <div>
                        •{" "}
                        {eligibility.policy.is_first_withdraw
                            ? "Первый вывод без комиссии"
                            : "Первый вывод уже был бесплатным, дальше действует шкала комиссий ниже"}
                    </div>
                    {eligibility.policy.fee_tiers.map((tier) => (
                        <div key={tier.min_amount}>
                            • От {formatBalance(tier.min_amount)} ⭐:{" "}
                            {tier.fee_xtr > 0
                                ? `${tier.fee_xtr} ${eligibility.policy.fee_currency}`
                                : "без комиссии"}
                        </div>
                    ))}
                    <div>
                        • Комиссия списывается только с баланса {eligibility.policy.fee_currency},
                        а не с игрового баланса звезд
                    </div>
                </div>
            </div>

            <div className="mt-4">
                <label className="text-xs uppercase tracking-wide text-white/50">
                    Метод вывода
                </label>
                <select
                    value={method}
                    onChange={(e) => setMethod(e.target.value as WithdrawalMethod)}
                    className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-3 text-sm text-white outline-none"
                >
                    <option value="stars">Stars</option>
                    <option value="ton">TON</option>
                </select>
            </div>

            <div className="mt-3">
                <label className="text-xs uppercase tracking-wide text-white/50">
                    Сумма
                </label>
                <input
                    type="number"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder={`Минимум ${formatBalance(eligibility.min_withdraw)}`}
                    className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-3 text-sm text-white outline-none placeholder:text-white/30"
                />
            </div>

            {method === "ton" && (
                <div className="mt-3">
                    <label className="text-xs uppercase tracking-wide text-white/50">
                        TON-кошелек
                    </label>
                    <input
                        value={wallet}
                        onChange={(e) => setWallet(e.target.value)}
                        placeholder="EQ..."
                        className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-3 text-sm text-white outline-none placeholder:text-white/30"
                    />
                    <div className="mt-2 text-xs text-white/40">
                        Укажи кошелек TON для получения выплаты
                    </div>
                </div>
            )}

            {method === "stars" && (
                <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-white/50">
                    Вывод в Stars создается заявкой и дальше обрабатывается админом
                </div>
            )}

            <button
                type="button"
                onClick={() => void handleSubmit()}
                disabled={!eligibility.can_withdraw || submitting}
                className="mt-4 w-full rounded-xl bg-white px-4 py-3 text-sm font-medium text-black transition disabled:cursor-not-allowed disabled:opacity-50"
            >
                {submitting ? "Отправка..." : "Создать заявку"}
            </button>

            {message && (
                <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/80">
                    {message}
                </div>
            )}

            <div className="mt-5">
                <div className="text-xs font-semibold uppercase tracking-wide text-white/50">
                    Мои заявки
                </div>

                {withdrawals.length === 0 ? (
                    <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/60">
                        У тебя пока нет заявок на вывод
                    </div>
                ) : (
                    <div className="mt-3 flex flex-col gap-3">
                        {withdrawals.map((item) => (
                            <div
                                key={item.id}
                                className="rounded-xl border border-white/10 bg-black/20 p-3"
                            >
                                <div className="flex items-center justify-between gap-3">
                                    <div className="text-sm font-medium text-white">
                                        {formatBalance(item.amount)} ⭐
                                    </div>
                                    <div className="text-xs text-white/60">
                                        {statusLabel(item.status)}
                                    </div>
                                </div>

                                <div className="mt-2 grid gap-1 text-xs text-white/60">
                                    <div>Метод: {methodLabel(item.method)}</div>
                                    <div>Создано: {item.created_at || "-"}</div>
                                    {item.processed_at ? <div>Обработано: {item.processed_at}</div> : null}
                                    {item.wallet ? <div>Кошелек: {item.wallet}</div> : null}
                                    <div>Комиссия: {feeAmountLabel(item)}</div>
                                    <div>Статус комиссии: {feeStatusLabel(item)}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
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

function formatBalance(value: number): string {
    return Number(value || 0).toFixed(2).replace(/\.00$/, "");
}

function statusLabel(status: string): string {
    switch (status) {
        case "pending":
            return "В обработке";
        case "approved":
            return "Одобрено";
        case "rejected":
            return "Отклонено";
        case "paid":
            return "Выплачено";
        case "cancelled":
            return "Отменено";
        default:
            return status;
    }
}

function methodLabel(method: string): string {
    switch (method) {
        case "ton":
            return "TON";
        case "stars":
            return "Stars";
        default:
            return method;
    }
}

function feeStatusLabel(item: WithdrawalItem): string {
    if (item.fee_refunded) return "возвращена";
    if (item.fee_paid) return "оплачена";
    if (Number(item.fee_xtr || 0) <= 0) return "не требуется";
    return "не оплачена";
}

function feeAmountLabel(item: WithdrawalItem): string {
    const fee = Number(item.fee_xtr || 0);
    if (fee <= 0) return "не требуется";
    return `${fee} XTR`;
}
