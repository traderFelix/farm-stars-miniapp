"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import RewardPopup from "@/components/RewardPopup";
import CampaignsPanel from "@/components/campaigns/CampaignsPanel";
import ReferralsPanel from "@/components/referrals/ReferralsPanel";
import WithdrawalPanel from "@/components/withdrawal/WithdrawalPanel";
import {
  authTelegram,
  abandonSubscriptionAssignment,
  cancelBattle,
  claimCheckin,
  claimSubscriptionDaily,
  clearAccessToken,
  type BattleRecentResult,
  getMyBattleStatus,
  getMySubscriptionStatus,
  getMyTheftStatus,
  getCheckinStatus,
  getMyProfile,
  joinSubscriptionTask,
  joinBattle,
  openBotTasks,
  startTheft,
  startTheftProtection,
  toUserErrorMessage,
  updateMyGameNickname,
  type BattleStatusResponse,
  type CheckinStatus,
  type Profile,
  type SubscriptionAssignmentItem,
  type SubscriptionStatusResponse,
  type SubscriptionTaskItem,
  type TheftStatusResponse,
} from "@/lib/api";
import { formatBalance, formatCompactBalance } from "@/lib/format";
import {
  closeTelegramMiniApp,
  getTelegramInitData,
  initTelegramMiniApp,
  openTelegramLink,
} from "@/lib/telegram";

type BootstrapState = "idle" | "loading" | "ready" | "error";
type AppTab = "profile" | "mining" | "referrals" | "campaigns" | "withdrawal";

type CheckinState = "idle" | "loading" | "ready" | "claiming" | "error";
type BattleLoadState = "idle" | "loading" | "ready" | "working" | "error";
type TheftLoadState = "idle" | "loading" | "ready" | "working" | "error";
type SubscriptionLoadState = "idle" | "loading" | "ready" | "working" | "error";
type SubscriptionActionContext =
  | { type: "task"; id: number }
  | { type: "assignment"; id: number }
  | { type: "abandon" };
type NicknameSaveState = "idle" | "saving";

const HERO_BANNER_URL = ["/hero", "mining-hero-banner.png"].join("/");
const BOT_USERNAME = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || "";
const BOT_TASKS_URL = BOT_USERNAME ? `https://t.me/${BOT_USERNAME}?start=tasks` : "";
const HERO_BANNER_STYLE = {
  backgroundImage: `linear-gradient(180deg, rgba(7, 10, 18, 0.04), rgba(7, 10, 18, 0.1)), url("${HERO_BANNER_URL}")`,
};
const BOOTSTRAP_ERROR_MESSAGE = "Сейчас не удалось открыть мини-приложение. Попробуй еще раз чуть позже.";

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
  const [battleStatus, setBattleStatus] = useState<BattleStatusResponse | null>(null);
  const [battleLoadState, setBattleLoadState] = useState<BattleLoadState>("idle");
  const [battleErrorMessage, setBattleErrorMessage] = useState("");
  const [battleDisplaySeconds, setBattleDisplaySeconds] = useState(0);
  const [theftStatus, setTheftStatus] = useState<TheftStatusResponse | null>(null);
  const [theftLoadState, setTheftLoadState] = useState<TheftLoadState>("idle");
  const [theftErrorMessage, setTheftErrorMessage] = useState("");
  const [theftNoticeMessage, setTheftNoticeMessage] = useState("");
  const [theftDisplaySeconds, setTheftDisplaySeconds] = useState(0);
  const [subscriptionStatus, setSubscriptionStatus] = useState<SubscriptionStatusResponse | null>(null);
  const [subscriptionLoadState, setSubscriptionLoadState] = useState<SubscriptionLoadState>("idle");
  const [subscriptionMessage, setSubscriptionMessage] = useState("");
  const [subscriptionRewardPopup, setSubscriptionRewardPopup] = useState<{
    amount: number;
    remaining: number;
  } | null>(null);
  const [subscriptionUnavailableTaskIds, setSubscriptionUnavailableTaskIds] = useState<Set<number>>(() => new Set());
  const [subscriptionTaskErrors, setSubscriptionTaskErrors] = useState<Record<number, string>>({});
  const [subscriptionAssignmentErrors, setSubscriptionAssignmentErrors] = useState<Record<number, string>>({});
  const [subscriptionAbandonError, setSubscriptionAbandonError] = useState("");
  const [subscriptionAbandonTarget, setSubscriptionAbandonTarget] = useState<SubscriptionAssignmentItem | null>(null);
  const [nicknameModalOpen, setNicknameModalOpen] = useState(false);
  const [nicknameDraft, setNicknameDraft] = useState("");
  const [nicknameSaveState, setNicknameSaveState] = useState<NicknameSaveState>("idle");
  const [nicknameErrorMessage, setNicknameErrorMessage] = useState("");
  const battleSyncInFlightRef = useRef(false);
  const theftSyncInFlightRef = useRef(false);
  const subscriptionSyncInFlightRef = useRef(false);

  const [debugMessage, setDebugMessage] = useState<string>("Шаг 1: запуск");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const operatorName = profile?.game_nickname || "Шахтер";

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
      const message = toUserErrorMessage(error, "Не удалось загрузить ежедневный бонус");
      setCheckin(null);
      setCheckinState("error");
      setCheckinMessage(message);
    }
  }

  async function loadBattleStatus(options?: { silent?: boolean }) {
    if (battleSyncInFlightRef.current) {
      return battleStatus;
    }

    battleSyncInFlightRef.current = true;

    if (!options?.silent) {
      setBattleLoadState("loading");
      setBattleErrorMessage("");
    }

    try {
      const status = await getMyBattleStatus();
      setBattleStatus(status);
      setBattleLoadState("ready");
      setBattleErrorMessage("");
      setProfile((prev) =>
        prev
          ? {
              ...prev,
              balance: Number(status.current_balance ?? prev.balance),
            }
          : prev,
      );
      return status;
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось загрузить статус дуэли");
      if (!options?.silent) {
        setBattleStatus(null);
        setBattleLoadState("error");
        setBattleErrorMessage(message);
        setBattleDisplaySeconds(0);
      }
      return battleStatus;
    } finally {
      battleSyncInFlightRef.current = false;
    }
  }

  async function handleJoinBattle() {
    if (battleLoadState === "working") return;

    try {
      setBattleLoadState("working");
      setBattleErrorMessage("");
      const status = await joinBattle();
      setBattleStatus(status);
      setBattleLoadState("ready");
      setProfile((prev) =>
        prev
          ? {
              ...prev,
              balance: Number(status.current_balance ?? prev.balance),
            }
          : prev,
      );
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось вступить в дуэль");
      setBattleLoadState("error");
      setBattleErrorMessage(message);
    }
  }

  async function handleCancelBattle() {
    if (battleLoadState === "working") return;

    try {
      setBattleLoadState("working");
      setBattleErrorMessage("");
      const status = await cancelBattle();
      setBattleStatus(status);
      setBattleLoadState("ready");
      setProfile((prev) =>
        prev
          ? {
              ...prev,
              balance: Number(status.current_balance ?? prev.balance),
            }
          : prev,
      );
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось отменить поиск соперника");
      setBattleLoadState("error");
      setBattleErrorMessage(message);
    }
  }

  async function loadTheftStatus(options?: { silent?: boolean }) {
    if (theftSyncInFlightRef.current) {
      return theftStatus;
    }

    theftSyncInFlightRef.current = true;

    if (!options?.silent) {
      setTheftLoadState("loading");
      setTheftErrorMessage("");
      setTheftNoticeMessage("");
    }

    try {
      const status = await getMyTheftStatus();
      setTheftStatus(status);
      setTheftLoadState("ready");
      setTheftErrorMessage("");
      if (options?.silent && status.state !== "active") {
        setTheftNoticeMessage("");
      }
      return status;
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось загрузить статус воровства");
      if (!options?.silent) {
        setTheftStatus(null);
        setTheftLoadState("error");
        setTheftErrorMessage(message);
        setTheftDisplaySeconds(0);
      }
      return theftStatus;
    } finally {
      theftSyncInFlightRef.current = false;
    }
  }

  async function handleStartTheft() {
    if (theftLoadState === "working") return;

    try {
      setTheftLoadState("working");
      setTheftErrorMessage("");
      setTheftNoticeMessage("");
      const result = await startTheft();
      setTheftStatus(result.status);
      setTheftLoadState("ready");
      if (result.ok) {
        setTheftNoticeMessage(result.message);
      } else {
        setTheftErrorMessage(result.message);
      }
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось начать воровство");
      setTheftLoadState("error");
      setTheftErrorMessage(message);
    }
  }

  async function handleStartTheftProtection() {
    if (theftLoadState === "working") return;

    try {
      setTheftLoadState("working");
      setTheftErrorMessage("");
      setTheftNoticeMessage("");
      const result = await startTheftProtection();
      setTheftStatus(result.status);
      setTheftLoadState("ready");
      if (result.ok) {
        setTheftNoticeMessage(result.message);
      } else {
        setTheftErrorMessage(result.message);
      }
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось включить защиту");
      setTheftLoadState("error");
      setTheftErrorMessage(message);
    }
  }

  async function loadSubscriptionStatus(options?: { silent?: boolean }) {
    if (subscriptionSyncInFlightRef.current) {
      return subscriptionStatus;
    }

    subscriptionSyncInFlightRef.current = true;

    if (!options?.silent) {
      setSubscriptionLoadState("loading");
      setSubscriptionMessage("");
    }

    try {
      const status = await getMySubscriptionStatus();
      setSubscriptionStatus(status);
      setSubscriptionUnavailableTaskIds(new Set());
      setSubscriptionTaskErrors({});
      setSubscriptionAssignmentErrors({});
      setSubscriptionAbandonError("");
      setSubscriptionLoadState("ready");
      if (!options?.silent) {
        setSubscriptionMessage("");
      }
      return status;
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось загрузить подписки");
      if (!options?.silent) {
        setSubscriptionStatus(null);
        setSubscriptionLoadState("error");
        setSubscriptionMessage(message);
      }
      return subscriptionStatus;
    } finally {
      subscriptionSyncInFlightRef.current = false;
    }
  }

  function applySubscriptionActionResult(result: {
    status: SubscriptionStatusResponse;
    balance: number;
    reward_granted: number;
    remaining_reward: number;
    message: string;
    ok: boolean;
  }, context?: SubscriptionActionContext) {
    setSubscriptionStatus(result.status);
    setSubscriptionLoadState("ready");
    setSubscriptionTaskErrors({});
    setSubscriptionAssignmentErrors({});
    setSubscriptionAbandonError("");
    setSubscriptionMessage("");
    setProfile((prev) =>
      prev
        ? {
            ...prev,
            balance: Number(result.balance ?? prev.balance),
          }
        : prev,
    );

    if (result.ok) {
      if (Number(result.reward_granted) > 0 || Number(result.remaining_reward) > 0) {
        setSubscriptionRewardPopup({
          amount: Number(result.reward_granted),
          remaining: Number(result.remaining_reward || 0),
        });
      }
      return;
    }

    if (context?.type === "task") {
      setSubscriptionTaskErrors({ [context.id]: result.message });
    } else if (context?.type === "assignment") {
      setSubscriptionAssignmentErrors({ [context.id]: result.message });
    } else if (context?.type === "abandon") {
      setSubscriptionAbandonError(result.message);
    } else {
      setSubscriptionMessage(result.message);
    }
  }

  async function handleJoinSubscription(task: SubscriptionTaskItem) {
    if (subscriptionLoadState === "working") return;

    try {
      setSubscriptionLoadState("working");
      setSubscriptionMessage("");
      setSubscriptionTaskErrors((prev) => {
        const next = { ...prev };
        delete next[task.id];
        return next;
      });
      const result = await joinSubscriptionTask(task.id);
      applySubscriptionActionResult(result, { type: "task", id: task.id });
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось проверить подписку");
      if (message.includes("Это задание временно недоступно")) {
        setSubscriptionUnavailableTaskIds((prev) => new Set(prev).add(task.id));
      }
      setSubscriptionLoadState("error");
      setSubscriptionMessage("");
      setSubscriptionTaskErrors((prev) => ({
        ...prev,
        [task.id]: message,
      }));
    }
  }

  async function handleClaimSubscription(assignment: SubscriptionAssignmentItem) {
    if (subscriptionLoadState === "working") return;

    try {
      setSubscriptionLoadState("working");
      setSubscriptionMessage("");
      setSubscriptionAssignmentErrors((prev) => {
        const next = { ...prev };
        delete next[assignment.id];
        return next;
      });
      const result = await claimSubscriptionDaily(assignment.id);
      applySubscriptionActionResult(result, { type: "assignment", id: assignment.id });
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось забрать награду");
      if (message.includes("Это задание временно недоступно")) {
        setSubscriptionUnavailableTaskIds((prev) => new Set(prev).add(assignment.task_id));
      }
      setSubscriptionLoadState("error");
      setSubscriptionMessage("");
      setSubscriptionAssignmentErrors((prev) => ({
        ...prev,
        [assignment.id]: message,
      }));
    }
  }

  async function handleConfirmAbandonSubscription() {
    if (!subscriptionAbandonTarget || subscriptionLoadState === "working") return;

    try {
      setSubscriptionLoadState("working");
      setSubscriptionMessage("");
      setSubscriptionAbandonError("");
      const result = await abandonSubscriptionAssignment(subscriptionAbandonTarget.id);
      setSubscriptionAbandonTarget(null);
      applySubscriptionActionResult(result, { type: "abandon" });
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось удалить задание");
      setSubscriptionLoadState("error");
      setSubscriptionMessage("");
      setSubscriptionAbandonError(message);
    }
  }

  function openSubscriptionAbandonModal(assignment: SubscriptionAssignmentItem) {
    setSubscriptionAbandonError("");
    setSubscriptionAbandonTarget(assignment);
  }

  function closeSubscriptionAbandonModal() {
    setSubscriptionAbandonError("");
    setSubscriptionAbandonTarget(null);
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
      const message = toUserErrorMessage(error, "Не удалось получить ежедневный бонус");
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
      if (!closed && BOT_TASKS_URL) {
        openTelegramLink(BOT_TASKS_URL);
      }
    } catch {
      if (BOT_TASKS_URL) {
        openTelegramLink(BOT_TASKS_URL);
      }
    } finally {
      setBotTasksOpening(false);
    }
  }

  function openNicknameModal() {
    setNicknameDraft(profile?.game_nickname || "");
    setNicknameErrorMessage("");
    setNicknameModalOpen(true);
  }

  async function handleSaveNickname() {
    if (!profile || nicknameSaveState === "saving") return;

    try {
      setNicknameSaveState("saving");
      setNicknameErrorMessage("");
      const nextProfile = await updateMyGameNickname(nicknameDraft);
      setProfile(nextProfile);
      setNicknameModalOpen(false);
    } catch (error) {
      const message = toUserErrorMessage(error, "Не удалось изменить игровой ник");
      setNicknameErrorMessage(message);
    } finally {
      setNicknameSaveState("idle");
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
          const message = "Открой мини-приложение из Telegram и попробуй еще раз.";
          setBootstrapState("error");
          setErrorMessage(message);
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

        setDebugMessage("Шаг 6: загрузка дуэли");
        await loadBattleStatus();
        if (cancelled) return;

        setDebugMessage("Шаг 7: загрузка воровства");
        await loadTheftStatus();
        if (cancelled) return;

        setDebugMessage("Шаг 8: загрузка подписок");
        await loadSubscriptionStatus();
        if (cancelled) return;

        setBootstrapState("ready");
        setDebugMessage("Шаг 9: готово");
      } catch (error) {
        if (cancelled) return;
        clearAccessToken();
        const message = toUserErrorMessage(error, BOOTSTRAP_ERROR_MESSAGE);
        setBootstrapState("error");
        setErrorMessage(message);
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (bootstrapState !== "ready" || activeTab !== "mining") return;
    void loadBattleStatus();
    void loadTheftStatus();
    void loadSubscriptionStatus();
  }, [activeTab, bootstrapState]);

  useEffect(() => {
    if (battleStatus?.state === "active") {
      setBattleDisplaySeconds(Math.max(Number(battleStatus.seconds_left) || 0, 0));
      return;
    }

    setBattleDisplaySeconds(0);
  }, [battleStatus?.battle_id, battleStatus?.seconds_left, battleStatus?.state]);

  useEffect(() => {
    if (battleStatus?.state !== "active") return;

    const timer = window.setInterval(() => {
      setBattleDisplaySeconds((prev) => Math.max(prev - 1, 0));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [battleStatus?.battle_id, battleStatus?.state]);

  useEffect(() => {
    if (theftStatus?.state === "active") {
      setTheftDisplaySeconds(Math.max(Number(theftStatus.seconds_left) || 0, 0));
      return;
    }

    setTheftDisplaySeconds(0);
  }, [
    theftStatus?.protection_attempt_id,
    theftStatus?.seconds_left,
    theftStatus?.state,
    theftStatus?.theft_id,
  ]);

  useEffect(() => {
    if (theftStatus?.state !== "active") return;

    const timer = window.setInterval(() => {
      setTheftDisplaySeconds((prev) => Math.max(prev - 1, 0));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [theftStatus?.protection_attempt_id, theftStatus?.state, theftStatus?.theft_id]);

  useEffect(() => {
    if (bootstrapState !== "ready" || activeTab !== "mining") return;
    if (!battleStatus || !["waiting", "active"].includes(battleStatus.state)) return;

    const timer = window.setInterval(() => {
      void loadBattleStatus({ silent: true });
    }, 8000);

    return () => window.clearInterval(timer);
  }, [activeTab, battleStatus?.battle_id, battleStatus?.state, bootstrapState]);

  useEffect(() => {
    if (bootstrapState !== "ready" || activeTab !== "mining") return;
    if (!theftStatus || theftStatus.state !== "active") return;

    const timer = window.setInterval(() => {
      void loadTheftStatus({ silent: true });
    }, 8000);

    return () => window.clearInterval(timer);
  }, [
    activeTab,
    bootstrapState,
    theftStatus?.protection_attempt_id,
    theftStatus?.state,
    theftStatus?.theft_id,
  ]);

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

      {subscriptionRewardPopup ? (
        <RewardPopup
          kicker="Награда за подписку"
          amountLabel={`+${formatCompactBalance(subscriptionRewardPopup.amount)} ⭐`}
          description={buildSubscriptionPopupDescription(subscriptionRewardPopup.remaining)}
          onClose={() => setSubscriptionRewardPopup(null)}
        />
      ) : null}

      {nicknameModalOpen && typeof document !== "undefined"
        ? createPortal(
            <div className="mining-modal-backdrop" role="presentation" onClick={() => setNicknameModalOpen(false)}>
              <div
                className="mining-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="game-nickname-modal-title"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="mining-kicker">Игровой ник</div>
                <h2 id="game-nickname-modal-title" className="mining-modal__title">
                  Сменить ник можно только один раз
                </h2>

                <input
                  type="text"
                  value={nicknameDraft}
                  maxLength={24}
                  placeholder="Новый игровой ник"
                  onChange={(event) => setNicknameDraft(event.target.value)}
                />

                {nicknameErrorMessage ? <StatusNote tone="error">{nicknameErrorMessage}</StatusNote> : null}

                <div className="mining-modal__actions">
                  <button
                    type="button"
                    className="mining-ghost-button"
                    onClick={() => setNicknameModalOpen(false)}
                    disabled={nicknameSaveState === "saving"}
                  >
                    Отмена
                  </button>
                  <button
                    type="button"
                    className="mining-primary-button"
                    onClick={() => void handleSaveNickname()}
                    disabled={nicknameSaveState === "saving"}
                  >
                    {nicknameSaveState === "saving" ? "Сохраняю..." : "Сохранить"}
                  </button>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}

      {subscriptionAbandonTarget && typeof document !== "undefined"
        ? createPortal(
            <div
              className="mining-modal-backdrop"
              role="presentation"
              onClick={closeSubscriptionAbandonModal}
            >
              <div
                className="mining-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="subscription-abandon-modal-title"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="mining-kicker">Подписка</div>
                <h2 id="subscription-abandon-modal-title" className="mining-modal__title">
                  Удалить задание?
                </h2>
                <p className="mining-modal__description">
                  Слот освободится сразу, но оставшаяся награда по этому заданию сгорит.
                </p>
                <div className="mining-modal__actions">
                  <div className="mining-modal__action">
                    <button
                      type="button"
                      className="mining-ghost-button"
                      onClick={closeSubscriptionAbandonModal}
                    >
                      Отмена
                    </button>
                  </div>
                  <div className="mining-modal__action">
                    <button
                      type="button"
                      className="mining-primary-button"
                      disabled={subscriptionLoadState === "working"}
                      onClick={() => void handleConfirmAbandonSubscription()}
                    >
                      {subscriptionLoadState === "working" ? "Удаляю..." : "Удалить"}
                    </button>
                    {subscriptionAbandonError ? (
                      <div className="mining-subscription-card__action-note" data-tone="error">
                        {subscriptionAbandonError}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}

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
              eyebrow="Запуск"
              title="Шахта сейчас недоступна"
              description="Попробуй открыть мини-приложение еще раз чуть позже"
            />
            <StatusNote tone="error">{errorMessage || BOOTSTRAP_ERROR_MESSAGE}</StatusNote>
            <button
              type="button"
              className="mining-primary-button mt-4 w-full"
              onClick={() => window.location.reload()}
            >
              Попробовать снова
            </button>
          </section>
        )}

        {bootstrapState === "ready" && profile && (
          <>
            {activeTab === "profile" && (
              <>
                <section className="mining-panel mining-profile-panel">
                  <div className="mining-profile-panel__header">
                    <div className="mining-profile-panel__name">{operatorName}</div>
                    <span className="mining-profile-panel__role">
                      {profile.role || "пользователь"}
                    </span>
                  </div>

                  <div className="mining-profile-panel__balance">
                    <div className="mining-profile-panel__balanceLabel">Баланс</div>
                    <div className="mining-profile-panel__balanceValue">
                      <span>{formatBalance(profile.balance)}</span>
                      <span>⭐</span>
                    </div>
                  </div>

                  {profile.can_change_game_nickname ? (
                    <button
                      type="button"
                      className="mining-profile-panel__edit"
                      onClick={openNicknameModal}
                    >
                      Сменить ник
                    </button>
                  ) : null}
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
              <>
                <section className="mining-panel">
                  <SectionHeader
                    title="Просмотр постов"
                    description="Открывай основной поток просмотров в боте"
                  />

                  <button
                    type="button"
                    onClick={() => void handleOpenBotTasks()}
                    disabled={botTasksOpening || battleLoadState === "working" || battleLoadState === "loading"}
                    className="mining-primary-button mt-4 w-full"
                  >
                    {botTasksOpening ? "Открываю..." : "Открыть просмотр постов"}
                  </button>
                </section>

                <section className="mining-panel">
                  <SectionHeader
                    title="Дуэль шахтеров"
                    description="Кто первым добьет 20 просмотров за 5 минут, тот победил"
                  />

                  <BattlePanel
                    status={battleStatus}
                    displaySeconds={battleDisplaySeconds}
                    loadState={battleLoadState}
                    errorMessage={battleErrorMessage}
                    botTasksOpening={botTasksOpening}
                    onJoin={() => void handleJoinBattle()}
                    onCancel={() => void handleCancelBattle()}
                    onOpenTasks={() => void handleOpenBotTasks()}
                  />
                </section>

                <section className="mining-panel">
                  <SectionHeader
                    title="Воровство"
                    description="Укради звезды или заряди защиту на сутки через просмотры постов"
                  />

                  <TheftPanel
                    status={theftStatus}
                    displaySeconds={theftDisplaySeconds}
                    loadState={theftLoadState}
                    errorMessage={theftErrorMessage}
                    noticeMessage={theftNoticeMessage}
                    botTasksOpening={botTasksOpening}
                    onStart={() => void handleStartTheft()}
                    onProtect={() => void handleStartTheftProtection()}
                    onOpenTasks={() => void handleOpenBotTasks()}
                  />
                </section>

                <section className="mining-panel">
                  <SectionHeader
                    title="Подписки"
                    description="Выбирай канал, подписывайся и забирай награду"
                    action={
                      subscriptionStatus ? (
                        <span className="mining-subscriptions-slots">
                          <span>Занято слотов </span>
                          <strong>
                            {subscriptionStatus.slots_used}/{subscriptionStatus.slot_limit}
                          </strong>
                        </span>
                      ) : null
                    }
                  />

                  <SubscriptionsPanel
                    status={subscriptionStatus}
                    loadState={subscriptionLoadState}
                    message={subscriptionMessage}
                    unavailableTaskIds={subscriptionUnavailableTaskIds}
                    taskErrors={subscriptionTaskErrors}
                    assignmentErrors={subscriptionAssignmentErrors}
                    onOpenChannel={(url) => openTelegramLink(url)}
                    onJoin={(task) => void handleJoinSubscription(task)}
                    onClaim={(assignment) => void handleClaimSubscription(assignment)}
                    onAbandon={openSubscriptionAbandonModal}
                  />
                </section>
              </>
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
                  title="Награды"
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
  eyebrow?: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        {eyebrow ? <div className="mining-kicker">{eyebrow}</div> : null}
        <h2 className={eyebrow ? "mt-1 text-xl font-semibold text-white" : "text-xl font-semibold text-white"}>
          {title}
        </h2>
        <p className="mt-1 text-sm text-slate-300">{description}</p>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
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
  compactValue = false,
}: {
  label: string;
  value: string;
  tone: "gold" | "cyan" | "slate";
  infoText?: string;
  compactValue?: boolean;
}) {
  return (
    <div className="mining-overview-card" data-tone={tone}>
      <div className="mining-overview-card__labelRow">
        <div className="mining-overview-card__label">{label}</div>
        {infoText ? <InfoHint text={infoText} /> : null}
      </div>
      <div className="mining-overview-card__value" data-compact={compactValue}>
        {value}
      </div>
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
        aria-label="Подробнее о доступности вывода"
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

function buildSubscriptionPopupDescription(remaining: number): string {
  if (remaining > 0) {
    return `Забирай награду каждый день, чтобы получить оставшиеся ${formatCompactBalance(remaining)} ⭐`;
  }

  return "Вся награда по этой подписке уже забрана";
}

function parseUtcTimestamp(value?: string | null): number | null {
  if (!value) return null;
  const normalized = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
  const parsed = Date.parse(normalized.endsWith("Z") ? normalized : `${normalized}Z`);
  return Number.isFinite(parsed) ? parsed : null;
}

function nextUtcMidnightMs(nowMs: number): number {
  const date = new Date(nowMs);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + 1);
}

function formatCountdown(totalMs: number): string {
  const totalSeconds = Math.max(Math.ceil(totalMs / 1000), 0);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

function getSubscriptionClaimWaitMs(assignment: SubscriptionAssignmentItem, nowMs: number): number {
  if (assignment.can_claim_today) return 0;
  if (assignment.daily_claims_done >= assignment.daily_claim_days) return 0;
  return Math.max(nextUtcMidnightMs(nowMs) - nowMs, 0);
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

function SubscriptionsPanel({
  status,
  loadState,
  message,
  unavailableTaskIds,
  taskErrors,
  assignmentErrors,
  onOpenChannel,
  onJoin,
  onClaim,
  onAbandon,
}: {
  status: SubscriptionStatusResponse | null;
  loadState: SubscriptionLoadState;
  message: string;
  unavailableTaskIds: Set<number>;
  taskErrors: Record<number, string>;
  assignmentErrors: Record<number, string>;
  onOpenChannel: (url: string) => void;
  onJoin: (task: SubscriptionTaskItem) => void;
  onClaim: (assignment: SubscriptionAssignmentItem) => void;
  onAbandon: (assignment: SubscriptionAssignmentItem) => void;
}) {
  const isBusy = loadState === "loading" || loadState === "working";
  const active = status?.active ?? [];
  const available = status?.available ?? [];
  const [activeExpanded, setActiveExpanded] = useState(false);
  const [availableExpanded, setAvailableExpanded] = useState(false);
  const [timerNowMs, setTimerNowMs] = useState(() => Date.now());
  const serverClockRef = useRef<{ source: string; serverMs: number; clientMs: number } | null>(null);
  const shouldRunCountdown = active.some(
    (assignment) => !assignment.can_claim_today && assignment.daily_claims_done < assignment.daily_claim_days,
  );
  const serverTime = status?.server_time || "";
  const parsedServerMs = parseUtcTimestamp(serverTime);

  if (serverTime && parsedServerMs !== null && serverClockRef.current?.source !== serverTime) {
    serverClockRef.current = {
      source: serverTime,
      serverMs: parsedServerMs,
      clientMs: Date.now(),
    };
  }

  const countdownNowMs = serverClockRef.current
    ? serverClockRef.current.serverMs + (timerNowMs - serverClockRef.current.clientMs)
    : timerNowMs;
  const visibleActive = activeExpanded ? active : active.slice(0, 1);
  const visibleAvailable = availableExpanded ? available : available.slice(0, 1);
  const hiddenActiveCount = Math.max(active.length - visibleActive.length, 0);
  const hiddenAvailableCount = Math.max(available.length - visibleAvailable.length, 0);

  useEffect(() => {
    if (active.length <= 1 && activeExpanded) {
      setActiveExpanded(false);
    }
  }, [active.length, activeExpanded]);

  useEffect(() => {
    if (available.length <= 1 && availableExpanded) {
      setAvailableExpanded(false);
    }
  }, [available.length, availableExpanded]);

  useEffect(() => {
    if (!shouldRunCountdown) return;
    setTimerNowMs(Date.now());
    const timerId = window.setInterval(() => {
      setTimerNowMs(Date.now());
    }, 1000);
    return () => window.clearInterval(timerId);
  }, [shouldRunCountdown]);

  if (loadState === "loading" && !status) {
    return <StatusNote>Ищу доступные задания подписки...</StatusNote>;
  }

  return (
    <div className="mt-4 space-y-4">
      {active.length > 0 || available.length > 0 ? (
        <div className="mining-subscriptions-board">
          {active.length > 0 ? (
            <section className="mining-subscriptions-section" data-kind="active">
              <div className="mining-subscriptions-section__head">
                <div>
                  <div className="mining-kicker">Мои подписки</div>
                  <h3>Забирай ежедневные награды</h3>
                </div>
              </div>
              <div className="mining-subscriptions-list">
                {visibleActive.map((assignment) => (
                  <SubscriptionActiveCard
                    key={assignment.id}
                    assignment={assignment}
                    nowMs={countdownNowMs}
                    disabled={isBusy}
                    unavailable={unavailableTaskIds.has(assignment.task_id)}
                    errorMessage={assignmentErrors[assignment.id] || ""}
                    onOpenChannel={onOpenChannel}
                    onClaim={onClaim}
                    onAbandon={onAbandon}
                  />
                ))}
                {active.length > 1 ? (
                  <button
                    type="button"
                    className="mining-subscriptions-toggle"
                    onClick={() => setActiveExpanded((value) => !value)}
                  >
                    {activeExpanded ? "Свернуть мои подписки" : `Показать еще ${hiddenActiveCount}`}
                  </button>
                ) : null}
              </div>
            </section>
          ) : null}

          {available.length > 0 ? (
            <section className="mining-subscriptions-section" data-kind="available">
              <div className="mining-subscriptions-section__head">
                <div>
                  <div className="mining-kicker">Новые подписки</div>
                  <h3>Выбери новое задание</h3>
                </div>
              </div>
              <div className="mining-subscriptions-list">
                {visibleAvailable.map((task) => (
                  <SubscriptionTaskCard
                    key={task.id}
                    task={task}
                    disabled={isBusy}
                    unavailable={unavailableTaskIds.has(task.id)}
                    errorMessage={taskErrors[task.id] || ""}
                    slotsFull={Boolean(status && status.slots_used >= status.slot_limit)}
                    onOpenChannel={onOpenChannel}
                    onJoin={onJoin}
                  />
                ))}
                {available.length > 1 ? (
                  <button
                    type="button"
                    className="mining-subscriptions-toggle"
                    onClick={() => setAvailableExpanded((value) => !value)}
                  >
                    {availableExpanded ? "Свернуть новые подписки" : `Показать еще ${hiddenAvailableCount}`}
                  </button>
                ) : null}
              </div>
            </section>
          ) : null}
        </div>
      ) : (
        <StatusNote>Пока нет подписок для добычи. Новые задания появятся здесь.</StatusNote>
      )}

      {message ? (
        <StatusNote tone={loadState === "error" ? "error" : "success"}>{message}</StatusNote>
      ) : null}
    </div>
  );
}

function SubscriptionTaskCard({
  task,
  disabled,
  unavailable,
  errorMessage,
  slotsFull,
  onOpenChannel,
  onJoin,
}: {
  task: SubscriptionTaskItem;
  disabled: boolean;
  unavailable: boolean;
  errorMessage: string;
  slotsFull: boolean;
  onOpenChannel: (url: string) => void;
  onJoin: (task: SubscriptionTaskItem) => void;
}) {
  const percent = Math.min((Math.max(task.participants_count, 0) / Math.max(task.max_subscribers, 1)) * 100, 100);

  return (
    <article className="mining-subscription-card">
      <div className="mining-subscription-card__top">
        <div>
          <div className="mining-kicker">Доступная подписка</div>
          <h3 className="mining-subscription-card__title">{task.title}</h3>
        </div>
        <div className="mining-subscription-card__reward">
          {formatCompactBalance(task.total_reward)} ⭐
        </div>
      </div>

      <div className="mining-subscription-card__limit">
        <span>Лимит</span>
        <strong>{task.participants_count}/{task.max_subscribers}</strong>
      </div>
      <div className="mining-subscription-card__track" aria-hidden="true">
        <span style={{ width: `${percent}%` }} />
      </div>

      <div className="mining-subscription-card__actions">
        <div className="mining-subscription-card__action">
          <button
            type="button"
            className="mining-secondary-button"
            disabled={disabled || unavailable || slotsFull}
            onClick={() => onOpenChannel(task.channel_url)}
          >
            Подписаться
          </button>
        </div>
        <div className="mining-subscription-card__action">
          <button
            type="button"
            className="mining-primary-button"
            disabled={disabled || unavailable || slotsFull}
            onClick={() => onJoin(task)}
            title={slotsFull ? "Все слоты подписок заняты" : undefined}
          >
            {slotsFull ? "Слоты заняты" : "Забрать награду"}
          </button>
          {slotsFull ? (
            <div className="mining-subscription-card__action-note" data-tone="info">
              Освободи слот, чтобы взять новое задание.
            </div>
          ) : errorMessage ? (
            <div className="mining-subscription-card__action-note" data-tone="error">
              {errorMessage}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function SubscriptionActiveCard({
  assignment,
  nowMs,
  disabled,
  unavailable,
  errorMessage,
  onOpenChannel,
  onClaim,
  onAbandon,
}: {
  assignment: SubscriptionAssignmentItem;
  nowMs: number;
  disabled: boolean;
  unavailable: boolean;
  errorMessage: string;
  onOpenChannel: (url: string) => void;
  onClaim: (assignment: SubscriptionAssignmentItem) => void;
  onAbandon: (assignment: SubscriptionAssignmentItem) => void;
}) {
  const percent = Math.min(
    (Math.max(assignment.daily_claims_done, 0) / Math.max(assignment.daily_claim_days, 1)) * 100,
    100,
  );
  const deleteTooltip = assignment.can_abandon
    ? "Удалить задание"
    : `Удаление доступно через ${Math.max(assignment.abandon_cooldown_days_left, 1)}д`;
  const claimWaitMs = getSubscriptionClaimWaitMs(assignment, nowMs);
  const canClaimNow = assignment.can_claim_today || claimWaitMs <= 0;
  const claimTimerLabel = canClaimNow ? "доступно" : formatCountdown(claimWaitMs);

  return (
    <article className="mining-subscription-card" data-active="true">
      <div className="mining-subscription-card__top">
        <div>
          <div className="mining-kicker">Активная подписка</div>
          <h3 className="mining-subscription-card__title">{assignment.title}</h3>
        </div>
        <button
          type="button"
          className="mining-subscription-delete"
          disabled={disabled || !assignment.can_abandon}
          data-tooltip={deleteTooltip}
          aria-label={deleteTooltip}
          onClick={() => onAbandon(assignment)}
        >
          <TrashIcon />
        </button>
      </div>

      <div className="mining-subscription-card__limit">
        <span>До следующего клейма</span>
        <strong>{claimTimerLabel}</strong>
      </div>
      <div
        className="mining-subscription-card__track"
        aria-label={`${assignment.daily_claims_done}/${assignment.daily_claim_days}`}
      >
        <span className="mining-subscription-card__track-fill" style={{ width: `${percent}%` }} />
        <span className="mining-subscription-card__track-value">
          {assignment.daily_claims_done}/{assignment.daily_claim_days}
        </span>
      </div>
      <p className="mining-subscription-card__hint">
        Осталось забрать {formatCompactBalance(assignment.remaining_reward)} ⭐
      </p>

      <div className="mining-subscription-card__actions">
        <div className="mining-subscription-card__action">
          <button
            type="button"
            className="mining-secondary-button"
            disabled={disabled || unavailable}
            onClick={() => onOpenChannel(assignment.channel_url)}
          >
            Подписаться
          </button>
        </div>
        <div className="mining-subscription-card__action">
          <button
            type="button"
            className="mining-primary-button"
            disabled={disabled || unavailable || !canClaimNow}
            onClick={() => onClaim(assignment)}
          >
            {canClaimNow ? "Забрать награду" : "Ждет таймер"}
          </button>
          {errorMessage ? (
            <div className="mining-subscription-card__action-note" data-tone="error">
              {errorMessage}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 18 18" aria-hidden="true" className="mining-subscription-delete__icon">
      <path
        d="M5.2 6.7h7.6l-.45 7.05a1.45 1.45 0 0 1-1.45 1.36H7.1a1.45 1.45 0 0 1-1.45-1.36L5.2 6.7Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.45"
        strokeLinejoin="round"
      />
      <path d="M4.2 4.7h9.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path
        d="M7.1 4.65V3.7c0-.42.34-.76.76-.76h2.28c.42 0 .76.34.76.76v.95"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.45"
        strokeLinecap="round"
      />
      <path d="M7.75 8.35v4.3M10.25 8.35v4.3" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" />
    </svg>
  );
}

function BattlePanel({
  status,
  displaySeconds,
  loadState,
  errorMessage,
  botTasksOpening,
  onJoin,
  onCancel,
  onOpenTasks,
}: {
  status: BattleStatusResponse | null;
  displaySeconds: number;
  loadState: BattleLoadState;
  errorMessage: string;
  botTasksOpening: boolean;
  onJoin: () => void;
  onCancel: () => void;
  onOpenTasks: () => void;
}) {
  const state = status?.state ?? "idle";
  const isBusy = loadState === "loading" || loadState === "working";

  if (loadState === "loading" && !status) {
    return <StatusNote>Поднимаю очередь дуэлей и синхронизирую твой матч...</StatusNote>;
  }

  const entryFee = status?.entry_fee ?? 1;
  const targetViews = Math.max(status?.target_views ?? 20, 1);
  const myProgress = Math.max(status?.my_progress ?? 0, 0);
  const opponentProgress = Math.max(status?.opponent_progress ?? 0, 0);
  const joinButtonLabel = getBattleJoinButtonLabel(status, loadState, entryFee);
  const leftPrimaryLabel = state === "active" ? `${myProgress}/${targetViews}` : `${status?.total_completed_views ?? 0}`;
  const leftPrimaryTitle = state === "active" ? "Твой прогресс" : "Всего просмотров";
  const rightPrimaryLabel = state === "active" ? `${opponentProgress}/${targetViews}` : `${formatCompactBalance(entryFee)} ⭐`;
  const rightPrimaryTitle =
    state === "active"
      ? status?.opponent_name
        ? `Соперник ${status.opponent_name}`
        : "Соперник"
      : "Плата за участие";
  const idleMessage = state === "idle" ? (status?.message || "").trim() : "";
  const idleMessageNormalized = idleMessage.toLowerCase();
  const idleMessageTone: "default" | "error" =
    idleMessageNormalized.includes("слишком част") || idleMessageNormalized.includes("не хватает")
    ? "error"
    : "default";

  return (
    <div className="mt-4 space-y-4">
      {state === "active" ? (
        <section className="mining-battle-race">
          <BattleProgressLane
            label={leftPrimaryTitle}
            value={leftPrimaryLabel}
            hint={buildBattleProgressHint(myProgress, targetViews)}
            progress={myProgress}
            total={targetViews}
            tone="gold"
          />
          <BattleProgressLane
            label={rightPrimaryTitle}
            value={rightPrimaryLabel}
            hint={buildBattleProgressHint(opponentProgress, targetViews)}
            progress={opponentProgress}
            total={targetViews}
            tone="cyan"
          />
          <div className="mining-battle-meta">
            <div className="mining-battle-meta__item" data-tone="slate">
              <div className="mining-battle-meta__label">Осталось</div>
              <div className="mining-battle-meta__value">{formatBattleCountdown(displaySeconds)}</div>
            </div>
            <div className="mining-battle-meta__item" data-tone="slate">
              <div className="mining-battle-meta__label">Банк</div>
              <div className="mining-battle-meta__value">{`${entryFee * 2} ⭐`}</div>
            </div>
          </div>
        </section>
      ) : (
        <section className="grid grid-cols-2 gap-3">
          <OverviewCard label={leftPrimaryTitle} value={leftPrimaryLabel} tone="gold" />
          <OverviewCard label={rightPrimaryTitle} value={rightPrimaryLabel} tone="cyan" />
        </section>
      )}

      {state === "waiting" ? (
        <BattleSearchStatus message={status?.message || "Ищу соперника для дуэли"} />
      ) : null}

      {status?.last_result ? (
        <StatusNote tone={status.last_result.result === "won" ? "success" : status.last_result.result === "lost" ? "error" : "default"}>
          {formatBattleRecentResult(status.last_result)}
        </StatusNote>
      ) : null}

      {loadState === "error" && errorMessage ? (
        <StatusNote tone="error">{errorMessage}</StatusNote>
      ) : null}

      {state === "idle" && (
        <div>
          <button
            type="button"
            onClick={onJoin}
            disabled={isBusy || !status?.can_join}
            className="mining-primary-button w-full"
          >
            {joinButtonLabel}
          </button>
          {idleMessage ? <StatusNote tone={idleMessageTone}>{idleMessage}</StatusNote> : null}
        </div>
      )}

      {state === "waiting" && (
        <div>
          <button
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            className="mining-ghost-button w-full"
          >
            Отменить поиск
          </button>
        </div>
      )}

      {state === "active" && (
        <div>
          <button
            type="button"
            onClick={onOpenTasks}
            disabled={botTasksOpening || isBusy}
            className="mining-primary-button w-full"
          >
            {botTasksOpening ? "Открываю..." : "Перейти к просмотру постов"}
          </button>
        </div>
      )}
    </div>
  );
}

function TheftPanel({
  status,
  displaySeconds,
  loadState,
  errorMessage,
  noticeMessage,
  botTasksOpening,
  onStart,
  onProtect,
  onOpenTasks,
}: {
  status: TheftStatusResponse | null;
  displaySeconds: number;
  loadState: TheftLoadState;
  errorMessage: string;
  noticeMessage: string;
  botTasksOpening: boolean;
  onStart: () => void;
  onProtect: () => void;
  onOpenTasks: () => void;
}) {
  const state = status?.state ?? "idle";
  const role = status?.role ?? null;
  const isBusy = loadState === "loading" || loadState === "working";
  const myProgress = Math.max(status?.my_progress ?? 0, 0);
  const targetViews = Math.max(status?.target_views ?? 5, 1);
  const opponentProgress = Math.max(status?.opponent_progress ?? 0, 0);
  const opponentTargetViews = Math.max(status?.opponent_target_views ?? 3, 1);
  const amount = Number(status?.amount ?? 0);
  const activeAmountLabel = role === "attacker" ? "Скрыто" : `${formatCompactBalance(amount)} ⭐`;
  const canAttack = Boolean(status?.can_attack) && !isBusy;
  const canProtect = Boolean(status?.can_protect) && !isBusy;

  if (loadState === "loading" && !status) {
    return <StatusNote>Проверяю, можно ли сейчас воровать или поставить защиту...</StatusNote>;
  }

  return (
    <div className="mt-4 space-y-4">
      {state === "active" ? (
        <section className="mining-battle-race">
          <StatusNote>{getTheftActiveTitle(role)}</StatusNote>

          <BattleProgressLane
            label={getTheftSelfLabel(role)}
            value={`${myProgress}/${targetViews}`}
            hint={buildBattleProgressHint(myProgress, targetViews)}
            progress={myProgress}
            total={targetViews}
            tone="gold"
          />

          {role !== "protector" ? (
            <BattleProgressLane
              label={getTheftOpponentLabel(role, status?.opponent_name)}
              value={`${opponentProgress}/${opponentTargetViews}`}
              hint={buildBattleProgressHint(opponentProgress, opponentTargetViews)}
              progress={opponentProgress}
              total={opponentTargetViews}
              tone="cyan"
            />
          ) : null}

          <div className="mining-battle-meta">
            <div className="mining-battle-meta__item" data-tone="slate">
              <div className="mining-battle-meta__label">Осталось</div>
              <div className="mining-battle-meta__value">{formatBattleCountdown(displaySeconds)}</div>
            </div>
            <div className="mining-battle-meta__item" data-tone="slate">
              <div className="mining-battle-meta__label">
                {role === "protector" ? "Защита" : role === "attacker" ? "Награда" : "Сумма"}
              </div>
              <div className="mining-battle-meta__value">
                {role === "protector" ? "24 часа" : activeAmountLabel}
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onOpenTasks}
            disabled={botTasksOpening || isBusy}
            className="mining-primary-button w-full"
          >
            {botTasksOpening ? "Открываю..." : "Перейти к просмотру постов"}
          </button>
        </section>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-3">
            <OverviewCard label="Кража" value={formatAvailability(status?.can_attack)} tone="gold" />
            <OverviewCard
              label="Защита"
              value={formatTheftProtectionCardValue(status)}
              tone="cyan"
              compactValue
            />
          </section>

          {state !== "protected" ? (
            <StatusNote>
              Чтобы украсть или защититься, нужно сделать 5 просмотров за 2 минуты
            </StatusNote>
          ) : null}

          {status?.last_result ? (
            <StatusNote tone={getTheftRecentResultTone(status.last_result)}>
              {formatTheftRecentResult(status.last_result)}
            </StatusNote>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={onStart}
              disabled={!canAttack}
              className="mining-primary-button w-full"
            >
              {getTheftAttackButtonLabel(status)}
            </button>
            <button
              type="button"
              onClick={onProtect}
              disabled={!canProtect}
              className="mining-secondary-button w-full"
            >
              {status?.can_protect === false ? "Защита активна" : "Защита на сутки"}
            </button>
          </div>
        </>
      )}

      {state !== "active" && noticeMessage ? <StatusNote tone="success">{noticeMessage}</StatusNote> : null}

      {errorMessage ? <StatusNote tone="error">{errorMessage}</StatusNote> : null}
    </div>
  );
}

function BattleProgressLane({
  label,
  value,
  hint,
  progress,
  total,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  progress: number;
  total: number;
  tone: "gold" | "cyan";
}) {
  const safeTotal = Math.max(total, 1);
  const percent = Math.min((Math.max(progress, 0) / safeTotal) * 100, 100);

  return (
    <div className="mining-battle-lane" data-tone={tone}>
      <div className="mining-battle-lane__top">
        <div className="mining-battle-lane__label">{label}</div>
        <div className="mining-battle-lane__value">{value}</div>
      </div>
      <div className="mining-battle-lane__track" aria-hidden="true">
        <div className="mining-battle-lane__fill" style={{ width: `${percent}%` }} />
      </div>
      <div className="mining-battle-lane__hint">{hint}</div>
    </div>
  );
}

function BattleSearchStatus({ message }: { message: string }) {
  return (
    <div className="mining-battle-search" role="status" aria-live="polite">
      <div className="mining-battle-search__header">
        <div className="mining-battle-search__title">{message}</div>
        <div className="mining-battle-search__dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </div>
      <div className="mining-battle-search__track" aria-hidden="true">
        <span className="mining-battle-search__beam" />
      </div>
    </div>
  );
}

function getBattleJoinButtonLabel(
  status: BattleStatusResponse | null,
  loadState: BattleLoadState,
  entryFee: number,
): string {
  if (status?.can_join) {
    return "Найти соперника";
  }

  if (!status && loadState === "error") {
    return "Дуэль недоступна";
  }

  if (status && Number(status.current_balance) < entryFee) {
    return "Нужна 1⭐";
  }

  return "Сейчас недоступно";
}

function getTheftAttackButtonLabel(status: TheftStatusResponse | null): string {
  if (status?.can_attack === false) {
    return "Уже сегодня воровал";
  }

  return "Украсть звезды";
}

function formatAvailability(value?: boolean): string {
  return value ? "0/1" : "1/1";
}

function formatTheftProtectionCardValue(status: TheftStatusResponse | null): string {
  return `${getRemainingProtectionHours(status)}/24 часа`;
}

function getRemainingProtectionHours(status: TheftStatusResponse | null): number {
  if (status?.state !== "protected" || !status.protected_until) {
    return 0;
  }

  const date = parseApiUtcDate(status.protected_until);
  if (Number.isNaN(date.getTime())) {
    return 24;
  }

  const diffMs = Math.max(date.getTime() - Date.now(), 0);
  return Math.min(Math.ceil(diffMs / 3_600_000), 24);
}

function getTheftRecentResultTone(
  result: NonNullable<TheftStatusResponse["last_result"]>,
): "default" | "error" | "success" {
  if (result.result === "stolen") {
    return result.role === "attacker" ? "success" : "error";
  }

  if (result.result === "defended") {
    return result.role === "victim" ? "success" : "default";
  }

  if (result.result === "protected") {
    return "success";
  }

  return "default";
}

function formatTheftRecentResult(result: NonNullable<TheftStatusResponse["last_result"]>): string {
  if (result.result === "stolen") {
    if (result.role === "attacker") {
      return `Кража удалась: +${formatCompactBalance(result.amount)} ⭐`;
    }

    return `У тебя украли ${formatCompactBalance(result.amount)} ⭐`;
  }

  if (result.result === "defended") {
    return result.role === "victim" ? "Ты отбил атаку" : "Кражу отбили";
  }

  if (result.result === "expired") {
    return "Кража сорвалась: время вышло";
  }

  return "Защита включена на сутки";
}

function getTheftActiveTitle(role: TheftStatusResponse["role"]): string {
  if (role === "attacker") {
    return "Кража запущена: сделай 5 просмотров быстрее, чем цель отобьет атаку.";
  }

  if (role === "victim") {
    return "На тебя напали: сделай 3 просмотра быстрее вора, чтобы отбить атаку.";
  }

  if (role === "protector") {
    return "Заряжаешь защиту: сделай 5 просмотров, чтобы включить антиворовство на сутки.";
  }

  return "Активность воровства уже идет.";
}

function getTheftSelfLabel(role: TheftStatusResponse["role"]): string {
  if (role === "victim") {
    return "Твоя оборона";
  }

  if (role === "protector") {
    return "Твоя защита";
  }

  return "Твоя кража";
}

function getTheftOpponentLabel(
  role: TheftStatusResponse["role"],
  opponentName?: string | null,
): string {
  if (role === "victim") {
    return opponentName ? `Вор ${opponentName}` : "Вор";
  }

  return opponentName ? `Цель ${opponentName}` : "Цель";
}

function buildBattleProgressHint(progress: number, total: number): string {
  const remaining = Math.max(total - progress, 0);
  if (remaining === 0) {
    return "Финиш достигнут";
  }

  return `До финиша ${remaining}`;
}

function formatBattleCountdown(seconds: number): string {
  const safeSeconds = Math.max(Number(seconds) || 0, 0);
  const minutes = Math.floor(safeSeconds / 60);
  const restSeconds = safeSeconds % 60;
  return `${minutes}:${String(restSeconds).padStart(2, "0")}`;
}

function parseApiUtcDate(value: string): Date {
  const normalized = value.trim();
  if (!normalized) {
    return new Date(Number.NaN);
  }

  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(normalized)) {
    return new Date(normalized);
  }

  const sqliteUtcMatch = normalized.match(
    /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.\d+)?$/,
  );
  if (sqliteUtcMatch) {
    return new Date(`${sqliteUtcMatch[1]}T${sqliteUtcMatch[2]}Z`);
  }

  return new Date(normalized);
}

function formatBattleRecentResult(result: BattleRecentResult): string {
  if (result.result === "won") {
    return `Последняя дуэль выиграна +${formatCompactBalance(result.delta)} ⭐`;
  }

  if (result.result === "lost") {
    return `Последняя дуэль проиграна ${formatCompactBalance(result.delta)} ⭐`;
  }

  return "Последняя дуэль завершилась вничью, ставка возвращена";
}
