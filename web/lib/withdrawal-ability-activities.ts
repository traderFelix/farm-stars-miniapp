export const WITHDRAWAL_ABILITY_ACTIVITIES = {
  viewPosts: "просмотры постов",
  dailyBonuses: "ежедневные бонусы",
  battles: "победы в дуэлях",
  theft: "воровство",
  subscriptions: "задания на подписки",
  referralWithdrawals: "выводы рефералов",
} as const;

export const WITHDRAWAL_ABILITY_ACTIVITY_LABELS = Object.values(
  WITHDRAWAL_ABILITY_ACTIVITIES,
);
