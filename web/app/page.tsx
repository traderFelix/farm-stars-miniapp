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
  const [logs, setLogs] = useState<string[]>([]);

  function log(message: string, data?: unknown) {
    const line =
        data === undefined ? message : `${message} ${JSON.stringify(data)}`;
    console.log(line);
    setLogs((prev) => [...prev, line]);
  }

  useEffect(() => {
    window.onerror = function (message, source, lineno, colno, error) {
      log("GLOBAL ERROR", {
        message,
        source,
        lineno,
        colno,
        error: error instanceof Error ? error.message : String(error),
      });
    };

    window.onunhandledrejection = function (event) {
      log("UNHANDLED PROMISE", event.reason);
    };
  }, []);

  useEffect(() => {
    async function bootstrap() {
      try {
        log("STEP 1: start");

        initTelegramWebApp();
        log("STEP 2: telegram ready");

        const initData = getTelegramInitData();
        console.log("INIT DATA RAW:", initData);
        console.log("INIT DATA LEN:", initData.length);
        setStatus(`initData len: ${initData.length}`);

        const payload = { init_data: initData };
        console.log("AUTH PAYLOAD:", payload);

        const auth = await apiPost<AuthResponse>("/auth/telegram", {
          init_data: initData,
        });
        log("STEP 4: auth ok", auth);

        localStorage.setItem("fs_token", auth.token);

        const profile = await apiGet<MeResponse>("/api/me", auth.token);
        log("STEP 5: profile ok", profile);

        setMe(profile);
        setStatus("Connected");
      } catch (error: any) {
        log("BOOTSTRAP ERROR", {
          message: error?.message,
          stack: error?.stack,
          cause: error?.cause,
        });

        setStatus(error?.message || "API error");
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

        <div style={{ marginTop: 24 }}>
          <h2>Debug logs</h2>
          <pre
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: 12,
                background: "#111",
                color: "#0f0",
                padding: 12,
                borderRadius: 8,
              }}
          >
          {logs.join("\n")}
        </pre>
        </div>
      </main>
  );
}