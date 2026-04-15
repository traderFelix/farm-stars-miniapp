"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import {
    createWithdrawal,
    getMyWithdrawals,
    getWithdrawalEligibility,
    toUserErrorMessage,
    type WithdrawalEligibilityResponse,
    type WithdrawalItem,
    type WithdrawalMethod,
} from "@/lib/api";
import { formatWithdrawalAbility, formatBalance } from "@/lib/format";

export default function WithdrawalPanel() {
    const [loading, setLoading] = useState(true);
    const [eligibility, setEligibility] =
        useState<WithdrawalEligibilityResponse | null>(null);
    const [withdrawals, setWithdrawals] = useState<WithdrawalItem[]>([]);
    const [feesExpanded, setFeesExpanded] = useState(false);

    const [method, setMethod] = useState<WithdrawalMethod>("stars");
    const [amount, setAmount] = useState<string>("");
    const [wallet, setWallet] = useState<string>("");

    const [submitting, setSubmitting] = useState(false);
    const [message, setMessage] = useState<string>("");
    const [messageTone, setMessageTone] = useState<"warning" | "error" | "success">("warning");

    async function loadPanelData(options?: { preserveMessage?: boolean }) {
        try {
            setLoading(true);

            if (!options?.preserveMessage) {
                setMessage("");
                setMessageTone("warning");
            }

            const [eligibilityData, myWithdrawalsData] = await Promise.all([
                getWithdrawalEligibility(),
                getMyWithdrawals(10),
            ]);

            setEligibility(eligibilityData);
            setWithdrawals(myWithdrawalsData.items || []);
        } catch (e) {
            setMessage(toUserErrorMessage(e, "Не удалось загрузить вывод"));
            setMessageTone("error");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void loadPanelData();
    }, []);

    async function handleSubmit() {
        const currentEligibility = eligibility;
        if (!currentEligibility) return;

        const amountNum = Number(amount);

        if (!amount || Number.isNaN(amountNum) || amountNum <= 0) {
            setMessage("Введите корректную сумму вывода");
            setMessageTone("warning");
            return;
        }

        if (amountNum < currentEligibility.min_withdraw) {
            setMessage(`Минимальная сумма вывода — ${formatBalance(currentEligibility.min_withdraw)}⭐️`);
            setMessageTone("warning");
            return;
        }

        if (amountNum > currentEligibility.available_balance) {
            setMessage("На балансе не хватает звезд для вывода");
            setMessageTone("warning");
            return;
        }

        if (method === "ton" && !wallet.trim()) {
            setMessage("Введите TON-кошелек");
            setMessageTone("warning");
            return;
        }

        if (!currentEligibility.can_withdraw) {
            setMessage(currentEligibility.message);
            setMessageTone("warning");
            return;
        }

        try {
            setSubmitting(true);
            setMessage("");
            setMessageTone("warning");

            const res = await createWithdrawal({
                method,
                amount: amountNum,
                wallet: method === "ton" ? wallet.trim() : null,
            });

            setMessage(res.message);
            setMessageTone("success");

            await loadPanelData({ preserveMessage: true });

            setAmount("");
            setWallet("");
        } catch (e) {
            setMessage(toUserErrorMessage(e, "Не удалось создать заявку"));
            setMessageTone("error");
        } finally {
            setSubmitting(false);
        }
    }

    if (loading) {
        return <div className="mining-status-note">Загрузка вывода...</div>;
    }

    if (!eligibility) {
        return (
            <div className="mining-status-note" data-tone="error">
                Не удалось загрузить вывод
            </div>
        );
    }

    const feeTiers = [...eligibility.policy.fee_tiers].sort((left, right) => right.min_amount - left.min_amount);

    return (
        <div>
            <div className="flex items-center justify-between gap-3">
                <div>
                    <h2 className="mt-1 text-xl font-semibold text-white">Центр вывода</h2>
                    <p className="mt-1 text-sm text-slate-300">
                        Выводи звезды или TON и следи за историей своих заявок
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => void loadPanelData({ preserveMessage: true })}
                    className="mining-ghost-button"
                    disabled={loading || submitting}
                >
                    Обновить
                </button>
            </div>

            <div className="mt-4">
                <WithdrawalAbilityMeter value={eligibility.withdrawal_ability} />
            </div>

            <div className="mining-surface-card">
                <div className="mining-overview-card__labelRow">
                    <button
                        type="button"
                        className="mining-surface-card__toggle"
                        aria-expanded={feesExpanded}
                        aria-controls="withdrawal-fees-panel"
                        onClick={() => setFeesExpanded((current) => !current)}
                    >
                        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                            Комиссии
                        </span>
                        <span className="mining-surface-card__toggleIcon" aria-hidden="true">
                            <svg viewBox="0 0 20 20" fill="none">
                                <path
                                    d="M5 7.5 10 12.5 15 7.5"
                                    stroke="currentColor"
                                    strokeWidth="1.9"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                />
                            </svg>
                        </span>
                    </button>
                </div>

                <div
                    id="withdrawal-fees-panel"
                    className={`mining-surface-card__collapse${feesExpanded ? " is-open" : ""}`}
                    aria-hidden={!feesExpanded}
                >
                    <div className="mining-surface-card__collapseInner">
                        <div className="mining-withdraw-rules">
                            <div className="mining-withdraw-rules__card">
                                <div className="mining-withdraw-rules__cardLabel">Первый вывод</div>
                                <div className="mining-withdraw-rules__cardValue">
                                    {eligibility.policy.is_first_withdraw ? "Без комиссии" : "Льгота уже использована"}
                                </div>
                                <div className="mining-withdraw-rules__cardText">
                                    {eligibility.policy.is_first_withdraw
                                        ? "Первая заявка проходит бесплатно"
                                        : "Дальше действует шкала комиссий ниже"}
                                </div>
                            </div>

                            <div className="mining-withdraw-rules__fees">
                                <div className="mining-withdraw-rules__cardLabel">Тарифы</div>

                                <div className="mining-withdraw-rules__tiers">
                                    {feeTiers.map((tier) => (
                                        <div key={tier.min_amount} className="mining-withdraw-rules__tier">
                                            <div className="mining-withdraw-rules__tierMin">
                                                От {formatBalance(tier.min_amount)} ⭐
                                            </div>
                                            <div className="mining-withdraw-rules__tierFee">
                                                {tier.fee_xtr > 0
                                                    ? `${tier.fee_xtr} ${eligibility.policy.fee_currency}`
                                                    : "Без комиссии"}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="mt-4">
                <div className="mining-overview-card__labelRow">
                    <label className="text-xs uppercase tracking-wide text-slate-400">
                        Метод вывода
                    </label>
                    <InfoHint
                        text={`Курс обмена в TON определяется по рынку ${eligibility.policy.rate_source_name}`}
                    />
                </div>
                <div className="mining-withdraw-selectWrap">
                    <select
                        value={method}
                        onChange={(e) => {
                            setMethod(e.target.value as WithdrawalMethod);
                            setMessage("");
                        }}
                        className="mining-withdraw-select"
                    >
                        <option value="stars">Звезды</option>
                        <option value="ton">TON</option>
                    </select>
                    <span className="mining-withdraw-selectIcon" aria-hidden="true">
                        <svg viewBox="0 0 20 20" fill="none">
                            <path
                                d="M5 7.5 10 12.5 15 7.5"
                                stroke="currentColor"
                                strokeWidth="1.9"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                            />
                        </svg>
                    </span>
                </div>
            </div>

            <div className="mt-3">
                <label className="text-xs uppercase tracking-wide text-slate-400">
                    Сумма в звездах
                </label>
                <input
                    type="number"
                    value={amount}
                    onChange={(e) => {
                        setAmount(e.target.value);
                        setMessage("");
                    }}
                    placeholder={`Минимум ${formatBalance(eligibility.min_withdraw)}`}
                    className="mining-withdraw-input mt-2"
                />
            </div>

            {method === "ton" && (
                <div className="mt-3">
                    <label className="text-xs uppercase tracking-wide text-slate-400">
                        TON-кошелек
                    </label>
                    <input
                        value={wallet}
                        onChange={(e) => {
                            setWallet(e.target.value);
                            setMessage("");
                        }}
                        placeholder="EQ..."
                        className="mining-withdraw-input mt-2"
                    />
                    <div className="mt-2 text-xs text-slate-500">
                        Укажи кошелек TON для получения выплаты
                    </div>
                </div>
            )}

            <button
                type="button"
                onClick={() => void handleSubmit()}
                disabled={submitting}
                className="mining-primary-button mt-4 w-full"
            >
                {submitting ? "Отправка..." : "Создать заявку"}
            </button>

            {message && (
                <div className="mining-status-note mt-4" data-tone={messageTone}>
                    {message}
                </div>
            )}

            <div className="mt-5">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Мои заявки
                </div>

                {withdrawals.length === 0 ? (
                    <div className="mining-note-card text-sm text-slate-300">
                        У тебя пока нет заявок на вывод
                    </div>
                ) : (
                    <div className="mt-3 flex flex-col gap-3">
                        {withdrawals.map((item) => (
                            <div
                                key={item.id}
                                className="mining-list-card"
                            >
                                <div className="flex items-center justify-between gap-3">
                                    <div className="text-sm font-medium text-white">
                                        {formatBalance(item.amount)} ⭐
                                    </div>
                                    <div className="text-xs text-slate-400">
                                        {statusLabel(item.status)}
                                    </div>
                                </div>

                                <div className="mt-2 grid gap-1 text-xs text-slate-300">
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

function WithdrawalAbilityMeter({ value }: { value: number }) {
    const normalizedValue = Math.min(Math.max(Number(value || 0), 0), 100);
    const tone =
        normalizedValue >= 100
            ? "green"
            : normalizedValue >= 66
              ? "yellow"
              : normalizedValue >= 33
                ? "orange"
                : "red";

    return (
        <section className="mining-withdraw-ability" data-tone={tone}>
            <div className="mining-withdraw-ability__header mining-overview-card__labelRow">
                <div className="mining-overview-card__label">Доступность вывода</div>
                <InfoHint text="Доступность вывода растет от просмотров, ежедневных бонусов, батлов и рефералов" />
            </div>

            <div className="mining-withdraw-ability__value">
                {formatWithdrawalAbility(normalizedValue)}
            </div>

            <div
                className="mining-withdraw-ability__track"
                role="progressbar"
                aria-label="Прогресс доступности вывода"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Number(normalizedValue.toFixed(2))}
            >
                <div
                    className="mining-withdraw-ability__fill"
                    style={{ width: `${normalizedValue}%` }}
                />
            </div>
        </section>
    );
}

function InfoHint({ text }: { text: string }) {
    const [open, setOpen] = useState(false);
    const [popoverStyle, setPopoverStyle] = useState<CSSProperties>({});
    const buttonRef = useRef<HTMLButtonElement | null>(null);
    const popoverRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (!open) return;

        function updatePosition() {
            const button = buttonRef.current;
            if (!button) return;

            const rect = button.getBoundingClientRect();
            const width = Math.min(248, Math.max(180, window.innerWidth - 32));
            const left = Math.min(
                window.innerWidth - width - 16,
                Math.max(16, rect.right - width + 10),
            );
            const top = Math.min(window.innerHeight - 16, rect.bottom + 10);

            setPopoverStyle({
                top: `${top}px`,
                left: `${left}px`,
                width: `${width}px`,
            });
        }

        function handlePointerDown(event: globalThis.MouseEvent | TouchEvent) {
            const target = event.target as Node | null;
            if (!target) return;
            if (buttonRef.current?.contains(target)) return;
            if (popoverRef.current?.contains(target)) return;
            setOpen(false);
        }

        function handleEscape(event: KeyboardEvent) {
            if (event.key === "Escape") {
                setOpen(false);
            }
        }

        updatePosition();
        window.addEventListener("resize", updatePosition);
        window.addEventListener("scroll", updatePosition, true);
        document.addEventListener("mousedown", handlePointerDown);
        document.addEventListener("touchstart", handlePointerDown);
        document.addEventListener("keydown", handleEscape);

        return () => {
            window.removeEventListener("resize", updatePosition);
            window.removeEventListener("scroll", updatePosition, true);
            document.removeEventListener("mousedown", handlePointerDown);
            document.removeEventListener("touchstart", handlePointerDown);
            document.removeEventListener("keydown", handleEscape);
        };
    }, [open]);

    return (
        <span
            className="mining-info-hint mining-info-hint--card"
            onMouseEnter={() => setOpen(true)}
            onMouseLeave={() => setOpen(false)}
        >
            <button
                type="button"
                className="mining-info-hint__button mining-info-hint__button--card"
                aria-label="Показать подсказку"
                aria-expanded={open}
                ref={buttonRef}
                onClick={() => setOpen((prev) => !prev)}
                onFocus={() => setOpen(true)}
                onBlur={() => setOpen(false)}
            >
                <InfoCircleIcon />
            </button>

            {open && typeof document !== "undefined"
                ? createPortal(
                    <div
                        ref={popoverRef}
                        className="mining-info-hint__popover mining-info-hint__popover--floating"
                        role="tooltip"
                        style={popoverStyle}
                    >
                        {text}
                    </div>,
                    document.body,
                )
                : null}
        </span>
    );
}

function InfoCircleIcon() {
    return (
        <svg
            viewBox="0 0 16 16"
            aria-hidden="true"
            className="mining-info-hint__icon"
        >
            <circle cx="8" cy="8" r="6.3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <circle cx="8" cy="4.55" r="0.95" fill="currentColor" />
            <path
                d="M8 6.9v4.05"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
            />
        </svg>
    );
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
            return "Звезды";
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
