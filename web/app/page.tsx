"use client";

import { useEffect, useState } from "react";

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
import { formatActivity, formatBalance } from "@/lib/format";
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

      setCheckinMessage(
        result.ok
          ? buildCheckinSuccessMessage(result.claimed_amount, tomorrowReward)
          : result.message,
      );

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
                      <div className="mt-4 grid grid-cols-2 gap-3">
                        <MiniStat
                          label="День цикла"
                          value={String(checkin.current_cycle_day)}
                          tone="slate"
                        />
                        <MiniStat
                          label="Сегодня"
                          value={`${formatBalance(checkin.reward_today)} ⭐`}
                          tone="gold"
                        />
                        <MiniStat
                          label="Завтра"
                          value={`${formatBalance(checkin.next_reward)} ⭐`}
                          tone="cyan"
                        />
                        <MiniStat
                          label="Статус"
                          value={checkin.can_claim ? "Можно забрать" : "Уже снято"}
                          tone="slate"
                        />
                      </div>

                      <button
                        type="button"
                        onClick={() => void handleClaimCheckin()}
                        disabled={!checkin.can_claim || checkinState === "claiming"}
                        className="mining-primary-button mt-4 w-full"
                      >
                        {checkinState === "claiming" ? "Добываю..." : "Забрать бонус"}
                      </button>

                      {checkinMessage && <StatusNote>{checkinMessage}</StatusNote>}
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
                  tab="referrals"
                  activeTab={activeTab}
                  title="Реф.бонус"
                  onSelect={setActiveTab}
                />
                <BottomTabButton
                  tab="campaigns"
                  activeTab={activeTab}
                  title="Конкурсы"
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
}: {
  label: string;
  value: string;
  tone: "gold" | "cyan" | "slate";
}) {
  return (
    <div className="mining-overview-card" data-tone={tone}>
      <div className="mining-overview-card__label">{label}</div>
      <div className="mining-overview-card__value">{value}</div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "gold" | "cyan" | "slate";
}) {
  return (
    <div className="mining-mini-stat" data-tone={tone}>
      <div className="mining-mini-stat__label">{label}</div>
      <div className="mining-mini-stat__value">{value}</div>
    </div>
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

function buildCheckinSuccessMessage(claimedAmount: number, nextReward: number): string {
  return [
    "Ежедневный бонус зачислен",
    `На баланс добавлено ${formatBalance(claimedAmount)} ⭐`,
    `Завтра будет доступно ${formatBalance(nextReward)} ⭐`,
  ].join("\n");
}
