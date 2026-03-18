"use client";

import { useEffect, useMemo, useState } from "react";
import { getTelegramWebApp, initTelegramMiniApp } from "@/lib/telegram";

export function StartCard() {
    const [isTelegram, setIsTelegram] = useState(false);
    const [userName, setUserName] = useState<string>("Гость");
    const [platform, setPlatform] = useState<string>("browser");

    useEffect(() => {
        const webApp = initTelegramMiniApp();

        if (!webApp) {
            setIsTelegram(false);
            return;
        }

        setIsTelegram(true);
        setPlatform(webApp.platform || "telegram");

        const tgUser = webApp.initDataUnsafe?.user;
        if (tgUser?.first_name) {
            setUserName(tgUser.first_name);
        }
    }, []);

    const badgeText = useMemo(() => {
        return isTelegram ? `Telegram · ${platform}` : "Обычный браузер";
    }, [isTelegram, platform]);

    const handleMainButtonDemo = () => {
        const webApp = getTelegramWebApp();
        if (!webApp) {
            alert("Открой Mini App внутри Telegram.");
            return;
        }

        webApp.HapticFeedback?.impactOccurred?.("light");
        webApp.showAlert?.("Mini App подключен. На следующем шаге сделаем auth.");
    };

    return (
        <section className="rounded-[28px] border border-white/10 bg-gradient-to-br from-white/10 to-white/5 p-4 shadow-soft backdrop-blur">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <div className="text-xs text-white/50">{badgeText}</div>
                    <h2 className="mt-2 text-xl font-semibold">Привет, {userName}</h2>
                    <p className="mt-2 text-sm leading-6 text-white/65">
                        Это стартовая заготовка Mini App. Здесь позже будет настоящий
                        главный экран, баланс и задания.
                    </p>
                </div>

                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10 text-xl">
                    ⭐
                </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">
                <button
                    type="button"
                    onClick={handleMainButtonDemo}
                    className="rounded-2xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:scale-[0.99] active:scale-[0.98]"
                >
                    Проверить WebApp
                </button>

                <button
                    type="button"
                    disabled
                    className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-white/45"
                >
                    Скоро: Start
                </button>
            </div>
        </section>
    );
}
