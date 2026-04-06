"use client";

import { useEffect, useMemo, useState } from "react";

import CampaignsPanel from "@/components/campaigns/CampaignsPanel";
import ReferralsPanel from "@/components/referrals/ReferralsPanel";
import WithdrawalPanel from "@/components/withdrawal/WithdrawalPanel";
import {
  authTelegram,
  checkTask,
  claimCheckin,
  clearAccessToken,
  getCheckinStatus,
  getMyProfile,
  getNextTask,
  openTask,
  type CheckinStatus,
  type Profile,
} from "@/lib/api";
import { clearOpenedTask, getOpenedTask, saveOpenedTask } from "@/lib/opened-task";
import type { TaskCheckResponse, TaskListItem } from "@/lib/tasks";
import { getTelegramInitData, initTelegramMiniApp } from "@/lib/telegram";

type BootstrapState = "idle" | "loading" | "ready" | "error";
type AppTab = "profile" | "mining" | "referrals" | "campaigns" | "withdrawal";

type TaskState =
  | "idle"
  | "loading"
  | "ready"
  | "opening"
  | "opened"
  | "checking"
  | "done"
  | "empty"
  | "error";

type CheckinState = "idle" | "loading" | "ready" | "claiming" | "error";

const HERO_BANNER_URL = ["/hero", "mining-hero-banner.png"].join("/");
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

  const [task, setTask] = useState<TaskListItem | null>(null);
  const [taskState, setTaskState] = useState<TaskState>("idle");
  const [openedAt, setOpenedAt] = useState<number | null>(null);
  const [taskMessage, setTaskMessage] = useState("");

  const [debugMessage, setDebugMessage] = useState<string>("Шаг 1: запуск");
  const [errorMessage, setErrorMessage] = useState<string>("");

  const elapsedSeconds = useElapsedSeconds(openedAt);
  const holdSeconds = task?.hold_seconds ?? 0;

  const remainingSeconds = useMemo(() => {
    return Math.max(0, holdSeconds - elapsedSeconds);
  }, [elapsedSeconds, holdSeconds]);

  const canCheck = Boolean(task && openedAt && remainingSeconds <= 0);
  const isTaskCompleted = Boolean(task?.already_completed || task?.status === "completed");
  const operatorName = profile?.first_name || profile?.username || "Felix";
  const taskReward = task ? formatBalance(task.reward) : "0";

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

      const result = await claimCheckin();

      setCheckinMessage(result.message);

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

  async function loadNextTask() {
    setTaskState("loading");
    setTaskMessage("");

    try {
      const nextTask = await getNextTask();

      if (!nextTask) {
        setTask(null);
        clearOpenedTask();
        setOpenedAt(null);
        setTaskState("empty");
        return;
      }

      setTask(nextTask);

      if (nextTask.already_completed || nextTask.status === "completed") {
        clearOpenedTask();
        setOpenedAt(null);
        setTaskState("done");
        setTaskMessage("Задание уже выполнено.");
        return;
      }

      const stored = getOpenedTask();
      if (stored && stored.task_id === nextTask.id) {
        setOpenedAt(stored.opened_at);
        setTaskState("opened");
        return;
      }

      if (stored && stored.task_id !== nextTask.id) {
        clearOpenedTask();
      }

      setOpenedAt(null);
      setTaskState("ready");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка загрузки задания";
      setTask(null);
      setTaskState("error");
      setTaskMessage(message);
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

        setDebugMessage("Шаг 6: загрузка заданий");
        await loadNextTask();
        if (cancelled) return;

        setBootstrapState("ready");
        setDebugMessage("Шаг 7: готово");
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

  async function handleOpenTask() {
    if (!task || isTaskCompleted) return;

    try {
      setTaskState("opening");
      setTaskMessage("");

      const result = await openTask(task.id, {
        source: "miniapp",
      });

      if (!result.ok) {
        setTaskState("done");
        setTaskMessage("Задание уже недоступно или было выполнено ранее.");
        await loadNextTask();
        return;
      }

      const openedTask = {
        task_id: result.task_id,
        opened_at: result.opened_at,
        hold_seconds: result.hold_seconds,
        can_check_at: result.can_check_at,
        session_id: result.session_id ?? null,
      };

      saveOpenedTask(openedTask);
      setOpenedAt(result.opened_at);
      setTaskState("opened");
      setTaskMessage("Пост открыт. Подожди нужное время и нажми проверить.");
      setActiveTab("mining");

      if (result.post_url) {
        window.open(result.post_url, "_blank", "noopener,noreferrer");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка открытия задания";
      setTaskState("error");
      setTaskMessage(message);
    }
  }

  async function handleCheckTask() {
    if (!task || isTaskCompleted) return;

    try {
      setTaskState("checking");
      setTaskMessage("");

      const stored = getOpenedTask();
      const result: TaskCheckResponse = await checkTask(task.id, {
        session_id: stored?.session_id ?? null,
      });

      setTaskMessage(result.message);

      if (result.status === "completed" || result.status === "already_completed") {
        clearOpenedTask();
        setOpenedAt(null);

        setProfile((prev) =>
          prev
            ? {
                ...prev,
                balance: Number(result.new_balance || prev.balance),
              }
            : prev,
        );

        await loadNextTask();
        return;
      }

      if (result.status === "too_early") {
        setTaskState("opened");
        return;
      }

      setTaskState("ready");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка проверки задания";
      setTaskState("error");
      setTaskMessage(message);
    }
  }

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
              description="Поднимаю мини-приложение Telegram, авторизацию и данные смены."
            />
            <StatusNote>{debugMessage}</StatusNote>
          </section>
        )}

        {bootstrapState === "error" && (
          <section className="mining-panel">
            <SectionHeader
              eyebrow="Сбой запуска"
              title="Не удалось запустить шахту"
              description="Проверь запуск из Telegram и токен, затем попробуй ещё раз."
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
                    hint="Текущий баланс пользователя"
                    tone="gold"
                  />
                  <OverviewCard
                    label="Активность"
                    value={formatActivity(profile.activity_index)}
                    hint="Индекс активности аккаунта"
                    tone="cyan"
                  />
                </section>

                <section className="mining-panel">
                  <SectionHeader
                    eyebrow="Ежедневный бонус"
                    title="Ежедневная добыча"
                    description="Забирай бонус за вход и следи за циклом без пропусков."
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
                  eyebrow="Контроль смены"
                  title="Просмотр постов"
                  description="Открывай пост, держи нужное время и подтверждай добычу."
                  action={
                    <button
                      type="button"
                      onClick={() => void loadNextTask()}
                      className="mining-ghost-button"
                      disabled={
                        taskState === "loading" ||
                        taskState === "opening" ||
                        taskState === "checking"
                      }
                    >
                      Обновить
                    </button>
                  }
                />

                {taskState === "loading" && (
                  <StatusNote>Подбираю следующую рабочую смену...</StatusNote>
                )}

                {taskState === "empty" && (
                  <StatusNote>Сейчас доступных заданий нет. Шахта пополняется.</StatusNote>
                )}

                {taskState === "error" && taskMessage && (
                  <StatusNote tone="error">{taskMessage}</StatusNote>
                )}

                {task && taskState !== "loading" && taskState !== "empty" && (
                  <>
                    <div className="mining-task-card">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <span className="mining-chip mining-chip--cyan">ЗАДАНИЕ НА ПРОСМОТР</span>
                          <div className="mt-3 text-2xl font-semibold text-white">{task.title}</div>
                          <div className="mt-2 text-sm text-slate-300">
                            {task.description || "Открой пост и подержи нужное время"}
                          </div>
                        </div>

                        <div className="mining-task-reward">
                          <span className="mining-task-reward__value">{taskReward}</span>
                          <span className="mining-task-reward__label">⭐ награда</span>
                        </div>
                      </div>

                      <div className="mt-5 grid grid-cols-2 gap-3">
                        <MiniStat
                          label="Удержание"
                          value={`${holdSeconds} сек`}
                          tone="slate"
                        />
                        <MiniStat
                          label="Статус"
                          value={taskStateLabel(taskState, isTaskCompleted)}
                          tone={canCheck ? "cyan" : "slate"}
                        />
                      </div>

                      {isTaskCompleted && (
                        <StatusNote tone="success">Задание уже выполнено</StatusNote>
                      )}

                      {!isTaskCompleted && openedAt && (
                        <div className="mt-4">
                          <div className="mining-progress">
                            <div
                              className="mining-progress__fill"
                              style={{
                                width: `${Math.min(
                                  100,
                                  holdSeconds > 0
                                    ? (elapsedSeconds / holdSeconds) * 100
                                    : 100,
                                )}%`,
                              }}
                            />
                          </div>
                          <div className="mt-2 text-sm text-slate-300">
                            {remainingSeconds > 0
                              ? `Подожди еще ${remainingSeconds} сек перед проверкой`
                              : "Можно проверять выполнение"}
                          </div>
                        </div>
                      )}

                      {!isTaskCompleted && (
                        <div className="mt-5 grid grid-cols-2 gap-3">
                          <button
                            type="button"
                            onClick={() => void handleOpenTask()}
                            disabled={taskState === "opening" || taskState === "checking"}
                            className="mining-primary-button"
                          >
                            {taskState === "opening" ? "Открываю..." : "Открыть пост"}
                          </button>

                          <button
                            type="button"
                            onClick={() => void handleCheckTask()}
                            disabled={
                              !canCheck || taskState === "opening" || taskState === "checking"
                            }
                            className="mining-secondary-button"
                          >
                            {taskState === "checking" ? "Проверяю..." : "Проверить"}
                          </button>
                        </div>
                      )}

                      {isTaskCompleted && (
                        <button
                          type="button"
                          onClick={() => void loadNextTask()}
                          className="mining-primary-button mt-5 w-full"
                        >
                          Следующее задание
                        </button>
                      )}
                    </div>

                    {taskMessage && <StatusNote>{taskMessage}</StatusNote>}
                  </>
                )}
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
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  tone: "gold" | "cyan" | "slate";
}) {
  return (
    <div className="mining-overview-card" data-tone={tone}>
      <div className="mining-overview-card__label">{label}</div>
      <div className="mining-overview-card__value">{value}</div>
      <div className="mining-overview-card__hint">{hint}</div>
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

function useElapsedSeconds(openedAt: number | null): number {
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));

  useEffect(() => {
    if (!openedAt) return;

    const timer = window.setInterval(() => {
      setNow(Math.floor(Date.now() / 1000));
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, [openedAt]);

  if (!openedAt) return 0;

  return Math.max(0, now - openedAt);
}

function formatBalance(value: number): string {
  return Number(value || 0)
    .toFixed(2)
    .replace(/\.00$/, "");
}

function formatActivity(value: number): string {
  const numeric = Number(value || 0);
  return `${numeric.toFixed(1)}%`;
}

function taskStateLabel(state: TaskState, completed: boolean): string {
  if (completed) return "Выполнено";

  switch (state) {
    case "loading":
      return "Загрузка";
    case "opening":
      return "Открываю";
    case "opened":
      return "Ожидание";
    case "checking":
      return "Проверка";
    case "error":
      return "Ошибка";
    case "empty":
      return "Пусто";
    case "done":
      return "Готово";
    default:
      return "Готово";
  }
}
