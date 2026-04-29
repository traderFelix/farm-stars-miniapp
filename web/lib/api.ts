const ACCESS_TOKEN_KEY = "farmstars_access_token";
const CLIENT_SESSION_KEY = "farmstars_client_session";

export type TelegramAuthResponse = {
    ok: boolean;
    token: string;
    session: {
        user_id: number;
        game_nickname?: string | null;
    };
};

export type Profile = {
    user_id: number;
    game_nickname?: string | null;
    game_nickname_change_count: number;
    can_change_game_nickname: boolean;
    balance: number;
    role: string;
    withdrawal_ability: number;
};

export type CheckinStatus = {
    can_claim: boolean;
    already_claimed_today: boolean;
    claimed_days_count: number;
    claimed_total_reward: number;
    season_length: number;
    cycle_rewards: Array<{
        day: number;
        reward: number;
        tier: string;
    }>;
    current_cycle_day: number;
    reward_today: number;
    next_cycle_day: number;
    next_reward: number;
    last_checkin_at?: string | null;
    server_time: string;
};

export type CheckinClaimResponse = {
    ok: boolean;
    claimed_amount: number;
    current_cycle_day: number;
    balance: number;
    claimed_at: string;
    message: string;
};

export type CampaignItem = {
    campaign_key: string;
    title: string;
    reward_amount: number;
    post_url?: string | null;
    post_button_url?: string | null;
    post_button_label?: string | null;
    is_winner: boolean;
    already_claimed: boolean;
};

export type CampaignListResponse = {
    items: CampaignItem[];
};

export type CampaignClaimResponse = {
    ok: boolean;
    message: string;
    new_balance: number;
    code?: string | null;
};

export type PromoRedeemResponse = {
    ok: boolean;
    message: string;
    new_balance: number;
    reward_amount: number;
    promo_code?: string | null;
    title?: string | null;
    code?: string | null;
};

export type ReferralMeResponse = {
    user_id: number;
    invited_count: number;
    reward_percent: number;
    invite_link: string;
    share_text: string;
};

export type WithdrawalMethod = "ton" | "stars";
export type WithdrawalStatus =
    | "pending"
    | "approved"
    | "rejected"
    | "paid"
    | "cancelled";

export type WithdrawalFeeTier = {
    min_amount: number;
    fee_xtr: number;
};

export type WithdrawalPolicy = {
    first_withdraw_free: boolean;
    is_first_withdraw: boolean;
    rate_source_name: string;
    rate_source_url: string;
    fee_currency: string;
    fee_balance_source: string;
    fee_tiers: WithdrawalFeeTier[];
};

export type WithdrawalEligibilityResponse = {
    can_withdraw: boolean;
    min_withdraw: number;
    min_task_percent: number;
    has_pending_withdrawal: boolean;
    account_age_hours: number;
    required_account_age_hours: number;
    withdrawal_ability: number;
    task_earnings_percent: number;
    available_balance: number;
    message: string;
    policy: WithdrawalPolicy;
};

export type WithdrawalCreateRequest = {
    method: WithdrawalMethod;
    amount: number;
    wallet?: string | null;
};

export type WithdrawalCreateResponse = {
    ok: boolean;
    withdrawal_id: number;
    status: WithdrawalStatus;
    message: string;
    balance?: number;
    fee_xtr?: number;
};

export type WithdrawalItem = {
    id: number;
    amount: number;
    method: WithdrawalMethod;
    status: WithdrawalStatus;
    wallet?: string | null;
    created_at: string;
    processed_at?: string | null;
    fee_xtr: number;
    fee_paid: boolean;
    fee_refunded: boolean;
};

export type WithdrawalListResponse = {
    items: WithdrawalItem[];
};

export type OpenBotTasksResponse = {
    ok: boolean;
};

export type BattleResult = "won" | "lost" | "draw";
export type BattleState = "idle" | "waiting" | "active";

export type BattleRecentResult = {
    result: BattleResult;
    finished_at: string;
    delta: number;
    stake_amount: number;
    opponent_name?: string | null;
};

export type BattleStatusResponse = {
    state: BattleState;
    battle_id?: number | null;
    target_views: number;
    entry_fee: number;
    duration_seconds: number;
    seconds_left: number;
    my_progress: number;
    opponent_progress: number;
    opponent_name?: string | null;
    current_balance: number;
    total_completed_views: number;
    can_join: boolean;
    can_cancel: boolean;
    can_open_tasks: boolean;
    hold_seconds_min: number;
    hold_seconds_max: number;
    message: string;
    last_result?: BattleRecentResult | null;
};

export type TheftState = "idle" | "active" | "protected";
export type TheftRole = "attacker" | "victim" | "protector";
export type TheftResult = "stolen" | "defended" | "expired" | "protected";

export type TheftRecentResult = {
    result: TheftResult;
    role: TheftRole;
    finished_at: string;
    amount: number;
    opponent_name?: string | null;
};

export type TheftStatusResponse = {
    state: TheftState;
    message: string;
    theft_id?: number | null;
    protection_attempt_id?: number | null;
    role?: TheftRole | null;
    amount: number;
    my_progress: number;
    target_views: number;
    opponent_progress: number;
    opponent_target_views: number;
    seconds_left: number;
    opponent_name?: string | null;
    protected_until?: string | null;
    can_attack: boolean;
    can_protect: boolean;
    last_result?: TheftRecentResult | null;
};

export type TheftActionResponse = {
    ok: boolean;
    message: string;
    status: TheftStatusResponse;
};

export type SubscriptionTaskItem = {
    id: number;
    title: string;
    channel_url: string;
    total_reward: number;
    participants_count: number;
    max_subscribers: number;
};

export type SubscriptionAssignmentItem = {
    id: number;
    task_id: number;
    title: string;
    channel_url: string;
    daily_claims_done: number;
    daily_claim_days: number;
    daily_reward_claimed: number;
    daily_reward_total: number;
    remaining_reward: number;
    can_claim_today: boolean;
    last_daily_claim_day?: string | null;
    can_abandon: boolean;
    abandon_available_at?: string | null;
    abandon_cooldown_days_left: number;
};

export type SubscriptionStatusResponse = {
    available: SubscriptionTaskItem[];
    active: SubscriptionAssignmentItem[];
    slots_used: number;
    slot_limit: number;
    abandon_available_at?: string | null;
    abandon_cooldown_days_left: number;
    server_time: string;
};

export type SubscriptionActionResponse = {
    ok: boolean;
    message: string;
    reward_granted: number;
    remaining_reward: number;
    balance: number;
    status: SubscriptionStatusResponse;
};

type RequestOptions = {
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    body?: unknown;
    auth?: boolean;
};

type ErrorPayload = {
    detail?: unknown;
    message?: unknown;
};

const GENERIC_SERVICE_ERROR = "Сервис временно недоступен. Попробуй еще раз чуть позже.";
const GENERIC_AUTH_ERROR = "Открой мини-приложение из Telegram и попробуй еще раз.";
const GENERIC_NOT_FOUND_ERROR = "Нужные данные сейчас недоступны.";
const GENERIC_RATE_LIMIT_ERROR = "Слишком много попыток. Попробуй чуть позже.";
const GENERIC_ACTION_ERROR = "Не удалось выполнить действие. Попробуй еще раз.";

export class ApiRequestError extends Error {
    status?: number;
    detail?: string;

    constructor(message: string, options?: { status?: number; detail?: string }) {
        super(message);
        this.name = "ApiRequestError";
        this.status = options?.status;
        this.detail = options?.detail;
    }
}

function isBrowser(): boolean {
    return typeof window !== "undefined";
}

export function setAccessToken(token: string): void {
    if (!isBrowser()) return;
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function getAccessToken(): string | null {
    if (!isBrowser()) return null;
    return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function clearAccessToken(): void {
    if (!isBrowser()) return;
    localStorage.removeItem(ACCESS_TOKEN_KEY);
}

function getClientSessionId(): string | null {
    if (!isBrowser()) return null;

    const existing = localStorage.getItem(CLIENT_SESSION_KEY);
    if (existing) {
        return existing;
    }

    const nextValue =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
            ? crypto.randomUUID()
            : `sess_${Math.random().toString(36).slice(2)}_${Date.now()}`;

    localStorage.setItem(CLIENT_SESSION_KEY, nextValue);
    return nextValue;
}

function buildHeaders(auth: boolean, hasBody: boolean): HeadersInit {
    const headers: HeadersInit = {};

    if (hasBody) {
        headers["Content-Type"] = "application/json";
    }

    if (auth) {
        const token = getAccessToken();
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }
    }

    const sessionId = getClientSessionId();
    if (sessionId) {
        headers["X-Client-Session"] = sessionId;
    }

    return headers;
}

function extractErrorDetail(data: unknown): string {
    if (data && typeof data === "object") {
        const payload = data as ErrorPayload;

        if (typeof payload.detail === "string" && payload.detail.trim()) {
            return payload.detail;
        }

        if (typeof payload.message === "string" && payload.message.trim()) {
            return payload.message;
        }
    }

    return "";
}

function containsCyrillic(value: string): boolean {
    return /[А-Яа-яЁёІіЇїЄє]/.test(value);
}

function isTechnicalErrorMessage(message: string): boolean {
    const normalized = message.trim().toLowerCase();
    if (!normalized) {
        return true;
    }

    const technicalMarkers = [
        "request failed with status",
        "failed to fetch",
        "networkerror",
        "unexpected token",
        "json",
        "traceback",
        "stack",
        "timeout",
        "timed out",
        "token",
        "authorization",
        "header",
        "session",
        "init_data",
        "telegram",
        "invalid",
        "expired",
        "missing",
        "not configured",
        "unavailable",
        "failed to",
        "internal",
        "proxy",
        "unsupported",
    ];

    if (technicalMarkers.some((marker) => normalized.includes(marker))) {
        return true;
    }

    return !containsCyrillic(message);
}

function fallbackMessageForStatus(status: number): string {
    if (status >= 500) {
        return GENERIC_SERVICE_ERROR;
    }

    if (status === 401) {
        return GENERIC_AUTH_ERROR;
    }

    if (status === 403) {
        return "Это действие сейчас недоступно.";
    }

    if (status === 404) {
        return GENERIC_NOT_FOUND_ERROR;
    }

    if (status === 429) {
        return GENERIC_RATE_LIMIT_ERROR;
    }

    return GENERIC_ACTION_ERROR;
}

function buildPublicErrorMessage(status: number, detail: string): string {
    const fallback = fallbackMessageForStatus(status);

    if (status === 401 || status >= 500) {
        return fallback;
    }

    if (detail && !isTechnicalErrorMessage(detail)) {
        return detail;
    }

    return fallback;
}

export function toUserErrorMessage(error: unknown, fallback: string = GENERIC_ACTION_ERROR): string {
    if (error instanceof ApiRequestError) {
        return error.message || fallback;
    }

    if (error instanceof Error) {
        const message = error.message.trim();
        if (message && !isTechnicalErrorMessage(message)) {
            return message;
        }
    }

    return fallback;
}

async function apiRequest<T>(
    path: string,
    { method = "GET", body, auth = false }: RequestOptions = {},
): Promise<T> {
    const hasBody = body !== undefined;

    let response: Response;
    try {
        response = await fetch(`/api${path}`, {
            method,
            headers: buildHeaders(auth, hasBody),
            body: hasBody ? JSON.stringify(body) : undefined,
            cache: "no-store",
        });
    } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        throw new ApiRequestError(GENERIC_SERVICE_ERROR, { detail });
    }

    let data: unknown;
    const contentType = response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
        data = await response.json();
    } else {
        const text = await response.text();
        data = text ? { detail: text } : null;
    }

    if (!response.ok) {
        const detail = extractErrorDetail(data);
        throw new ApiRequestError(buildPublicErrorMessage(response.status, detail), {
            status: response.status,
            detail,
        });
    }

    return data as T;
}

export async function authTelegram(
    initData: string,
): Promise<TelegramAuthResponse> {
    const result = await apiRequest<TelegramAuthResponse>("/auth/telegram", {
        method: "POST",
        body: {
            init_data: initData,
        },
        auth: false,
    });

    if (!result?.token) {
        throw new ApiRequestError(GENERIC_AUTH_ERROR);
    }

    setAccessToken(result.token);
    return result;
}

export async function getMyProfile(): Promise<Profile> {
    return apiRequest<Profile>("/profile/me", {
        method: "GET",
        auth: true,
    });
}

export async function updateMyGameNickname(gameNickname: string): Promise<Profile> {
    return apiRequest<Profile>("/profile/me/game-nickname", {
        method: "PATCH",
        body: {
            game_nickname: gameNickname,
        },
        auth: true,
    });
}

export async function openBotTasks(): Promise<OpenBotTasksResponse> {
    return apiRequest<OpenBotTasksResponse>("/tasks/open-in-bot", {
        method: "POST",
        auth: true,
    });
}

export async function getMyBattleStatus(): Promise<BattleStatusResponse> {
    return apiRequest<BattleStatusResponse>("/battles/me", {
        method: "GET",
        auth: true,
    });
}

export async function joinBattle(): Promise<BattleStatusResponse> {
    return apiRequest<BattleStatusResponse>("/battles/join", {
        method: "POST",
        auth: true,
    });
}

export async function cancelBattle(): Promise<BattleStatusResponse> {
    return apiRequest<BattleStatusResponse>("/battles/cancel", {
        method: "POST",
        auth: true,
    });
}

export async function getMyTheftStatus(): Promise<TheftStatusResponse> {
    return apiRequest<TheftStatusResponse>("/thefts/me", {
        method: "GET",
        auth: true,
    });
}

export async function startTheft(): Promise<TheftActionResponse> {
    return apiRequest<TheftActionResponse>("/thefts/start", {
        method: "POST",
        auth: true,
    });
}

export async function startTheftProtection(): Promise<TheftActionResponse> {
    return apiRequest<TheftActionResponse>("/thefts/protect", {
        method: "POST",
        auth: true,
    });
}

export async function getMySubscriptionStatus(): Promise<SubscriptionStatusResponse> {
    return apiRequest<SubscriptionStatusResponse>("/subscriptions/me", {
        method: "GET",
        auth: true,
    });
}

export async function joinSubscriptionTask(taskId: number): Promise<SubscriptionActionResponse> {
    return apiRequest<SubscriptionActionResponse>(`/subscriptions/${taskId}/join`, {
        method: "POST",
        auth: true,
    });
}

export async function claimSubscriptionDaily(assignmentId: number): Promise<SubscriptionActionResponse> {
    return apiRequest<SubscriptionActionResponse>(`/subscriptions/assignments/${assignmentId}/claim`, {
        method: "POST",
        auth: true,
    });
}

export async function abandonSubscriptionAssignment(assignmentId: number): Promise<SubscriptionActionResponse> {
    return apiRequest<SubscriptionActionResponse>(`/subscriptions/assignments/${assignmentId}/abandon`, {
        method: "POST",
        auth: true,
    });
}

export async function getCheckinStatus(): Promise<CheckinStatus> {
    return apiRequest<CheckinStatus>("/checkin/status", {
        method: "GET",
        auth: true,
    });
}

export async function claimCheckin(): Promise<CheckinClaimResponse> {
    return apiRequest<CheckinClaimResponse>("/checkin/claim", {
        method: "POST",
        auth: true,
    });
}

export async function getActiveCampaigns(): Promise<CampaignListResponse> {
    return apiRequest<CampaignListResponse>("/campaigns/active", {
        method: "GET",
        auth: true,
    });
}

export async function claimCampaign(
    campaignKey: string,
): Promise<CampaignClaimResponse> {
    return apiRequest<CampaignClaimResponse>(`/campaigns/${campaignKey}/claim`, {
        method: "POST",
        auth: true,
    });
}

export async function redeemPromo(code: string): Promise<PromoRedeemResponse> {
    return apiRequest<PromoRedeemResponse>("/promos/redeem", {
        method: "POST",
        body: { code },
        auth: true,
    });
}

export async function getMyReferrals(): Promise<ReferralMeResponse> {
    return apiRequest<ReferralMeResponse>("/referrals/me", {
        method: "GET",
        auth: true,
    });
}

export async function getWithdrawalEligibility(): Promise<WithdrawalEligibilityResponse> {
    return apiRequest<WithdrawalEligibilityResponse>("/withdrawals/eligibility", {
        method: "GET",
        auth: true,
    });
}

export async function createWithdrawal(
    payload: WithdrawalCreateRequest,
): Promise<WithdrawalCreateResponse> {
    return apiRequest<WithdrawalCreateResponse>("/withdrawals", {
        method: "POST",
        body: payload,
        auth: true,
    });
}

export async function getMyWithdrawals(
    limit: number = 20,
): Promise<WithdrawalListResponse> {
    return apiRequest<WithdrawalListResponse>(`/withdrawals/my?limit=${limit}`, {
        method: "GET",
        auth: true,
    });
}
