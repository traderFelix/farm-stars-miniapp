"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import RewardPopup from "@/components/RewardPopup";
import CampaignsPanel from "@/components/campaigns/CampaignsPanel";
import ReferralsPanel from "@/components/referrals/ReferralsPanel";
import WithdrawalPanel from "@/components/withdrawal/WithdrawalPanel";
import {
  authTelegram,
  claimCheckin,
  clearAccessToken,
  getCheckinStatus,
  getMyProfile,
  openBotTasks,
  type CheckinStatus,
  type Profile,
} from "@/lib/api";
import { formatActivity, formatBalance, formatCompactBalance } from "@/lib/format";
import {
  closeTelegramMiniApp,
  getTelegramInitData,
  initTelegramMiniApp,
  openTelegramLink,
} from "@/lib/telegram";

type BootstrapState = "idle" | "loading" | "ready" | "error";
type AppTab = "profile" | "mining" | "referrals" | "campaigns" | "withdrawal";

type CheckinState = "idle" | "loading" | "ready" | "claiming" | "error";

const HERO_BANNER_URL = ["/hero", "mining-hero-banner.png"].join("/");
const BOT_USERNAME = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || "felix_farm_stars_bot";
const BOT_TASKS_URL = `https://t.me/${BOT_USERNAME}?start=tasks`;
const HERO_BANNER_STYLE = {
  backgroundImage: `linear-gradient(180deg, rgba(7, 10, 18, 0.04), rgba(7, 10, 18, 0.1)), url("${HERO_BANNER_URL}")`,
};

export default function HomePage() {
  const [bootstrapState, setBootstrapState] = useState<BootstrapState>("idle");
  const [activeTab, setActiveTab] = useState<AppTab>("profile");
  const [profile, setProfile] = useState<Profile | null>(null);

  const [checkin, setCheckin] = useState<CheckinStatus | null>(null);
  const [checkinState, setCheckinState] = useState<CheckinState>("idle");
  const [checkinMessage, setCheckinMessage] = useState("");
  const [checkinRewardPopup, setCheckinRewardPopup] = useState<{
    claimedAmount: number;
    nextCycleDay: number;
    nextReward: number;
  } | null>(null);
  const [botTasksOpening, setBotTasksOpening] = useState(false);

  const [debugMessage, setDebugMessage] = useState<string>("Шаг 1: запуск");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const operatorName = profile?.first_name || profile?.username || "Felix";

  async function loadCheckinStatus(options?: { preserveMessage?: boolean }) {
    setCheckinState("loading");
    if (!options?.preserveMessage) {
      setCheckinMessage("");
    }

    try {
      const status = await getCheckinStatus();
      setCheckin(status);
      setCheckinState("ready");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка загрузки ежедневного бонуса";
      setCheckin(null);
      setCheckinState("error");
      setCheckinMessage(message);
    }
  }

  async function handleClaimCheckin() {
    if (!checkin?.can_claim || checkinState === "claiming") return;

    try {
      setCheckinState("claiming");
      setCheckinMessage("");
      const tomorrowReward = checkin?.next_reward ?? 0;

      const result = await claimCheckin();

      if (result.ok) {
        setCheckinRewardPopup({
          claimedAmount: result.claimed_amount,
          nextCycleDay: checkin?.next_cycle_day ?? 1,
          nextReward: tomorrowReward,
        });
      } else {
        setCheckinMessage(result.message);
      }

      setProfile((prev) =>
        prev
          ? {
              ...prev,
              balance: Number(result.balance ?? prev.balance),
            }
          : prev,
      );

      await loadCheckinStatus({ preserveMessage: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка получения ежедневного бонуса";
      setCheckinState("error");
      setCheckinMessage(message);
    }
  }

  async function handleOpenBotTasks() {
    if (botTasksOpening) return;

    try {
      setBotTasksOpening(true);
      await openBotTasks();

      const closed = closeTelegramMiniApp();
      if (!closed) {
        openTelegramLink(BOT_TASKS_URL);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Не удалось открыть поток постов";
      openTelegramLink(BOT_TASKS_URL);
      window.alert(message);
    } finally {
      setBotTasksOpening(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        setBootstrapState("loading");
        setErrorMessage("");
        setDebugMessage("Шаг 1: запуск");

        initTelegramMiniApp();
        if (cancelled) return;

        setDebugMessage("Шаг 2: Telegram готов");

        const initData = getTelegramInitData();
        if (!initData) {
          const message = "Не пришли данные запуска из Telegram";
          setBootstrapState("error");
          setErrorMessage(message);
          setDebugMessage(`Ошибка запуска: ${message}`);
          return;
        }

        setDebugMessage("Шаг 3: авторизация");
        await authTelegram(initData);
        if (cancelled) return;

        setDebugMessage("Шаг 4: загрузка профиля");
        const nextProfile = await getMyProfile();
        if (cancelled) return;
        setProfile(nextProfile);

        setDebugMessage("Шаг 5: загрузка ежедневного бонуса");
        await loadCheckinStatus({ preserveMessage: true });
        if (cancelled) return;

        setBootstrapState("ready");
        setDebugMessage("Шаг 6: готово");
      } catch (error) {
        if (cancelled) return;
        clearAccessToken();
        const message = error instanceof Error ? error.message : "Неизвестная ошибка запуска";
        setBootstrapState("error");
        setErrorMessage(message);
        setDebugMessage(`Ошибка запуска: ${message}`);
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mining-app">
      {checkinRewardPopup ? (
        <RewardPopup
          kicker="Ежедневный бонус зачислен"
          amountLabel={`+${formatCompactBalance(checkinRewardPopup.claimedAmount)} ⭐`}
          description={buildCheckinPopupDescription(
            checkinRewardPopup.nextCycleDay,
            checkinRewardPopup.nextReward,
          )}
          onClose={() => setCheckinRewardPopup(null)}
        />
      ) : null}

      <div className="mining-app__mesh" aria-hidden="true" />
      <div className="mining-app__orb mining-app__orb--gold" aria-hidden="true" />
      <div className="mining-app__orb mining-app__orb--cyan" aria-hidden="true" />
      <div className="mining-app__orb mining-app__orb--bottom" aria-hidden="true" />

      <div className="mining-shell mx-auto flex min-h-screen max-w-md flex-col gap-4 px-4 py-5 pt-safe-top">
        <header className="mining-hero-art" aria-label="Баннер шахты">
          <div className="mining-hero-art__image" style={HERO_BANNER_STYLE} aria-hidden="true" />
        </header>

        {bootstrapState === "loading" && (
          <section className="mining-panel">
            <SectionHeader
              eyebrow="Запуск"
              title="Подключаю шахтный контур"
              description="Поднимаю мини-приложение Telegram, авторизацию и данные смены"
            />
            <StatusNote>{debugMessage}</StatusNote>
          </section>
        )}

        {bootstrapState === "error" && (
          <section className="mining-panel">
            <SectionHeader
              eyebrow="Сбой запуска"
              title="Не удалось запустить шахту"
              description="Проверь запуск из Telegram и токен, затем попробуй ещё раз"
            />
            <StatusNote tone="error">{debugMessage}</StatusNote>
            <StatusNote tone="error">{errorMessage}</StatusNote>
          </section>
        )}

        {bootstrapState === "ready" && profile && (
          <>
            {activeTab === "profile" && (
              <>
                <section className="mining-panel mining-profile-panel">
                  <div className="mining-profile-panel__name">{operatorName}</div>
                  <span className="mining-profile-panel__role">
                    {profile.role || "пользователь"}
                  </span>
                </section>

                <section className="grid grid-cols-2 gap-3">
                  <OverviewCard
                    label="Баланс"
                    value={`${formatBalance(profile.balance)} ⭐`}
                    tone="gold"
                  />
                  <OverviewCard
                    label="Индекс активности"
                    value={formatActivity(profile.activity_index)}
                    tone="cyan"
                    infoText="Индекс активности растет от просмотра постов, ежедневных бонусов и рефералов"
                  />
                </section>

                <section className="mining-panel">
                  <SectionHeader
                    eyebrow="Ежедневный бонус"
                    title="Ежедневная добыча"
                    description="Забирай бонус за вход и следи за циклом без пропусков"
                    action={
                      <button
                        type="button"
                        onClick={() => void loadCheckinStatus()}
                        className="mining-ghost-button"
                        disabled={checkinState === "loading" || checkinState === "claiming"}
                      >
                        Обновить
                      </button>
                    }
                  />

                  {checkinState === "loading" && (
                    <StatusNote>Сканирую суточный цикл добычи...</StatusNote>
                  )}

                  {checkinState === "error" && (
                    <StatusNote tone="error">
                      {checkinMessage || "Не удалось загрузить ежедневный бонус"}
                    </StatusNote>
                  )}

                  {checkin && checkinState !== "loading" && (
                    <>
                      <CheckinSeasonBoard checkin={checkin} />

                      <button
                        type="button"
                        onClick={() => void handleClaimCheckin()}
                        disabled={!checkin.can_claim || checkinState === "claiming"}
                        className="mining-primary-button mt-4 w-full"
                      >
                        {checkinState === "claiming" ? "Добываю..." : "Забрать бонус"}
                      </button>

                      {checkinMessage && <StatusNote tone="error">{checkinMessage}</StatusNote>}
                    </>
                  )}
                </section>
              </>
            )}

            {activeTab === "mining" && (
              <section className="mining-panel">
                <SectionHeader
                  eyebrow=""
                  title="Просмотр постов"
                  description="Этот сценарий перенесен в бота, чтобы просмотры и начисления работали корректно"
                />

                <button
                  type="button"
                  onClick={() => void handleOpenBotTasks()}
                  disabled={botTasksOpening}
                  className="mining-primary-button mt-4 w-full"
                >
                  {botTasksOpening ? "Открываю просмотр постов..." : "Открыть просмотр постов"}
                </button>
              </section>
            )}

            {activeTab === "withdrawal" && (
              <section className="mining-panel">
                <WithdrawalPanel />
              </section>
            )}

            {activeTab === "referrals" && (
              <section className="mining-panel">
                <ReferralsPanel />
              </section>
            )}

            {activeTab === "campaigns" && (
              <section className="mining-panel">
                <CampaignsPanel
                  onBalanceChange={(nextBalance) =>
                    setProfile((prev) =>
                      prev
                        ? {
                            ...prev,
                            balance: Number(nextBalance),
                          }
                        : prev,
                    )
                  }
                />
              </section>
            )}

            <nav className="mining-bottom-nav" aria-label="Нижняя навигация">
              <div className="mining-bottom-nav__inner">
                <BottomTabButton
                  tab="profile"
                  activeTab={activeTab}
                  title="Профиль"
                  onSelect={setActiveTab}
                />
                <BottomTabButton
                  tab="mining"
                  activeTab={activeTab}
                  title="Добыча"
                  onSelect={setActiveTab}
                />
                <BottomTabButton
                  tab="campaigns"
                  activeTab={activeTab}
                  title="Конкурсы"
                  onSelect={setActiveTab}
                />
                <BottomTabButton
                  tab="referrals"
                  activeTab={activeTab}
                  title="Реф.бонус"
                  onSelect={setActiveTab}
                />
                <BottomTabButton
                  tab="withdrawal"
                  activeTab={activeTab}
                  title="Вывод"
                  onSelect={setActiveTab}
                />
              </div>
            </nav>
          </>
        )}
      </div>
    </main>
  );
}

function SectionHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <div className="mining-kicker">{eyebrow}</div>
        <h2 className="mt-1 text-xl font-semibold text-white">{title}</h2>
        <p className="mt-1 text-sm text-slate-300">{description}</p>
      </div>
      {action}
    </div>
  );
}

function BottomTabButton({
  tab,
  activeTab,
  title,
  onSelect,
}: {
  tab: AppTab;
  activeTab: AppTab;
  title: string;
  onSelect: (tab: AppTab) => void;
}) {
  const active = tab === activeTab;

  return (
    <button
      type="button"
      className="mining-bottom-tab"
      data-active={active}
      onClick={() => onSelect(tab)}
    >
      <span className="mining-bottom-tab__dot" aria-hidden="true" />
      <span className="mining-bottom-tab__title">{title}</span>
    </button>
  );
}

function OverviewCard({
  label,
  value,
  tone,
  infoText,
}: {
  label: string;
  value: string;
  tone: "gold" | "cyan" | "slate";
  infoText?: string;
}) {
  return (
    <div className="mining-overview-card" data-tone={tone}>
      <div className="mining-overview-card__labelRow">
        <div className="mining-overview-card__label">{label}</div>
        {infoText ? <InfoHint text={infoText} /> : null}
      </div>
      <div className="mining-overview-card__value">{value}</div>
    </div>
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

    function handlePointerDown(event: MouseEvent | TouchEvent) {
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
        aria-label="Подробнее об индексе активности"
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

function StatusNote({
  children,
  tone = "default",
}: {
  children: React.ReactNode;
  tone?: "default" | "error" | "success";
}) {
  return (
    <div className="mining-status-note mt-4" data-tone={tone}>
      {children}
    </div>
  );
}

function CheckinSeasonBoard({ checkin }: { checkin: CheckinStatus }) {
  const claimedLabel = `${checkin.claimed_days_count}/${checkin.season_length}`;
  const totalCycleReward = checkin.cycle_rewards.reduce((total, item) => total + item.reward, 0);
  const claimedRewardLabel = `${formatCompactBalance(checkin.claimed_total_reward)}/${formatCompactBalance(totalCycleReward)}`;

  return (
    <div className="mt-4">
      <div className="mining-checkin-hero">
        <div className="mining-overview-card mining-checkin-hero__card" data-tone="gold">
          <div className="mining-overview-card__label">Добыто за цикл</div>
          <div className="mining-overview-card__value mining-checkin-hero__value">
            <RewardInline value={claimedRewardLabel} />
          </div>
        </div>

        <div className="mining-overview-card mining-checkin-hero__card" data-tone="cyan">
          <div className="mining-overview-card__label">Заклеймлено</div>
          <div className="mining-overview-card__value">{claimedLabel}</div>
        </div>
      </div>

      <div className="mining-checkin-board">
        {checkin.cycle_rewards.map((item) => (
          <CheckinRewardCell key={item.day} item={item} checkin={checkin} />
        ))}
      </div>
    </div>
  );
}

function CheckinRewardCell({
  item,
  checkin,
}: {
  item: CheckinStatus["cycle_rewards"][number];
  checkin: CheckinStatus;
}) {
  const state = getCheckinRewardState(item.day, checkin);
  const placement = getCheckinRewardPlacement(item.day);

  return (
    <div
      className="mining-checkin-day"
      data-state={state}
      data-tier={item.tier}
      data-day={item.day}
      data-large={item.day === 30}
      style={placement}
    >
      <div className="mining-checkin-day__top">
        <span className="mining-checkin-day__number">№{item.day}</span>
      </div>
      <div className="mining-checkin-day__reward">
        <span className="mining-checkin-day__rewardValue">{formatCompactBalance(item.reward)}</span>
        <span className="mining-checkin-day__rewardStar">⭐</span>
      </div>
    </div>
  );
}

function getCheckinRewardState(
  day: number,
  checkin: CheckinStatus,
): "claimed" | "claimable" | "upcoming" {
  if (day <= checkin.claimed_days_count) {
    return "claimed";
  }

  if (day === checkin.current_cycle_day && checkin.can_claim) {
    return "claimable";
  }

  return "upcoming";
}

function getCheckinRewardPlacement(day: number) {
  const fixedPlacement: Record<number, { gridColumn: string; gridRow: string }> = {
    7: { gridColumn: "7", gridRow: "1" },
    14: { gridColumn: "7", gridRow: "2" },
    21: { gridColumn: "7", gridRow: "3" },
    26: { gridColumn: "2", gridRow: "5" },
    27: { gridColumn: "3", gridRow: "5" },
    28: { gridColumn: "4", gridRow: "5" },
    29: { gridColumn: "1", gridRow: "5" },
    30: { gridColumn: "5 / span 3", gridRow: "4 / span 2" },
  };

  if (fixedPlacement[day]) {
    return fixedPlacement[day];
  }

  if (day <= 6) {
    return {
      gridColumn: String(day),
      gridRow: "1",
    };
  }

  if (day <= 13) {
    return {
      gridColumn: String(day - 7),
      gridRow: "2",
    };
  }

  if (day <= 20) {
    return {
      gridColumn: String(day - 14),
      gridRow: "3",
    };
  }

  return {
    gridColumn: String(day - 21),
    gridRow: "4",
  };
}

function buildCheckinPopupDescription(nextCycleDay: number, nextReward: number): string {
  if (nextCycleDay === 30) {
    return `Завтра откроется джекпот ${formatCompactBalance(nextReward)} ⭐`;
  }

  if ([7, 14, 21].includes(nextCycleDay)) {
    return `Завтра откроется буст ${formatCompactBalance(nextReward)} ⭐`;
  }

  return `Завтра будет доступно ${formatCompactBalance(nextReward)} ⭐`;
}

function RewardInline({
  value,
  compact = false,
}: {
  value: string;
  compact?: boolean;
}) {
  return (
    <span className="mining-inline-reward" data-compact={compact}>
      <span className="mining-inline-reward__value">{value}</span>
      <span className="mining-inline-reward__star">⭐</span>
    </span>
  );
}
