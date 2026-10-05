import { useEffect, useRef } from "react";
import { api, type RankingRow } from "../api";

/** Observer del ranking para estudiantes y administración. */
export function useRankingLive(updateRows: (rows: RankingRow[]) => void): void {
  const updateRef = useRef(updateRows);
  updateRef.current = updateRows;

  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let delay = 2000;

    const refresh = async () => {
      try {
        const response = await api.ranking();
        if (!stopped) updateRef.current(response.rows);
      } catch { /* Se conserva el último ranking visible durante una caída. */ }
    };

    const scheduleRetry = () => {
      if (stopped || retry !== null) return;
      retry = setTimeout(() => {
        retry = null;
        void connect();
      }, delay);
      delay = Math.min(delay * 2, 30000);
    };

    async function connect() {
      try {
        // El ticket viaja en cookie HttpOnly; nunca se agrega un JWT a la URL.
        const ticket = await api.rankingSession();
        if (stopped) return;
        if (ticket.websocket_path !== "/api/v1/ws/ranking") {
          scheduleRetry();
          return;
        }
        const protocol = location.protocol === "https:" ? "wss" : "ws";
        const current = new WebSocket(`${protocol}://${location.host}${ticket.websocket_path}`);
        socket = current;
        current.onopen = () => { delay = 2000; };
        current.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === "ranking.updated" && Array.isArray(payload.rows)) {
              updateRef.current(payload.rows);
            }
          } catch { /* Un evento inválido no interrumpe la sesión. */ }
        };
        current.onerror = () => current.close();
        current.onclose = () => {
          if (socket === current) socket = null;
          if (!stopped) {
            void refresh();
            scheduleRetry();
          }
        };
      } catch {
        if (!stopped) {
          void refresh();
          scheduleRetry();
        }
      }
    }

    const onVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisibility);
    void connect();

    return () => {
      stopped = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (retry !== null) clearTimeout(retry);
      socket?.close();
    };
  }, []);
}
