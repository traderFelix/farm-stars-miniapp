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
