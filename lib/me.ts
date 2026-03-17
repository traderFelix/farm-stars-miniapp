export type MeResponse = {
    ok: true;
    user: {
        id: number;
        username?: string | null;
        first_name?: string | null;
        last_name?: string | null;
        balance: number;
        role: string;
        activity_index: number;
    };
};
