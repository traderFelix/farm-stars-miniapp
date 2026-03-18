"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { getTelegramInitData, initTelegramWebApp } from "@/lib/telegram";

type AuthResponse = {
  ok: boolean;
  token: string;
  session: {
    user_id: number;
    username?: string;
    first_name?: string;
  };
};

type MeResponse = {
  id: number;
  username?: string;
  first_name?: string;
  role: string;
  balance: number;
};

export default function HomePage() {
  const [status, setStatus] = useState("Loading...");
  const [me, setMe] = useState<MeResponse | null>(null);

  useEffect(() => {
    async function bootstrap() {
      try {
        initTelegramWebApp();

        const initData = getTelegramInitData();

        const auth = await apiPost<AuthResponse>("/auth/telegram", {
          init_data: initData,
        });

        localStorage.setItem("fs_token", auth.token);

        const profile = await apiGet<MeResponse>("/api/me", auth.token);

        setMe(profile);
        setStatus("Connected");
      } catch (error) {
        console.error(error);
        setStatus("API error");
      }
    }

    bootstrap();
  }, []);

  return (
      <main style={{ padding: 24 }}>
        <h1>Farm Stars</h1>
        <p>{status}</p>

        {me && (
            <>
              <p>User ID: {me.id}</p>
              <p>Username: {me.username || "-"}</p>
              <p>Balance: {me.balance}</p>
              <p>Role: {me.role}</p>
            </>
        )}
      </main>
  );
}