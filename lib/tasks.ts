export type NextTaskResponse = {
    ok: true;
    task: {
        id: number;
        type: "view_post";
        title: string;
        reward: number;
        hold_seconds: number;
        telegram_url: string;
        channel_name?: string | null;
        message_id?: number | null;
    } | null;
};

export type TaskOpenResponse = {
    ok: true;
    opened_at: number;
};

export type TaskCheckResponse = {
    ok: true;
    reward: number;
    new_balance: number;
    message: string;
};
