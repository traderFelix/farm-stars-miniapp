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
    activity_index: number;
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
    activity_index: number;
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

type RequestOptions = {
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    body?: unknown;
    auth?: boolean;
};

type ErrorPayload = {
    detail?: unknown;
    message?: unknown;
};

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

function extractErrorMessage(data: unknown, status: number): string {
    if (data && typeof data === "object") {
        const payload = data as ErrorPayload;

        if (typeof payload.detail === "string" && payload.detail.trim()) {
            return payload.detail;
        }

        if (typeof payload.message === "string" && payload.message.trim()) {
            return payload.message;
        }
    }

    return `Request failed with status ${status}`;
}

async function apiRequest<T>(
    path: string,
    { method = "GET", body, auth = false }: RequestOptions = {},
): Promise<T> {
    const hasBody = body !== undefined;

    const response = await fetch(`/api${path}`, {
        method,
        headers: buildHeaders(auth, hasBody),
        body: hasBody ? JSON.stringify(body) : undefined,
        cache: "no-store",
    });

    let data: unknown;
    const contentType = response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
        data = await response.json();
    } else {
        const text = await response.text();
        data = text ? { detail: text } : null;
    }

    if (!response.ok) {
        throw new Error(extractErrorMessage(data, response.status));
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
        throw new Error("Token was not returned by /auth/telegram");
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
