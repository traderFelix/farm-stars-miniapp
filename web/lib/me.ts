export type MeResponse = {
    ok: true;
    user: {
        id: number;
        game_nickname?: string | null;
        balance: number;
        role: string;
        withdrawal_ability: number;
    };
};
