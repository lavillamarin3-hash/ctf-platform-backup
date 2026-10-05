// ============================================================
// CONTROLADOR DEL JUGADOR
// Responsabilidad: estado, carga de datos y acciones del jugador.
// No contiene JSX. Las vistas reciben este contrato.
// ============================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, BackendLaboratory, Challenge, RankingRow, Run } from "../api";
import { PlayerView } from "../config";
import { inferCategory } from "../components/challenges";
import { observeAssignedChallenges, publishNotification } from "../lib/notifications";
import { useRankingLive } from "../lib/useRankingLive";

export function usePlayerController(userId: number) {
  const [view, setView] = useState<PlayerView>("dashboard");
  const [menuOpen, setMenuOpen] = useState(false);
  const [challenges, setChallenges] = useState<Challenge[]>([]);
  const [ranking, setRanking] = useState<RankingRow[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [laboratories, setLaboratories] = useState<BackendLaboratory[]>([]);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [filter, setFilter] = useState("Todas");
  const [categoryFilter, setCategoryFilter] = useState("Todas");
  const [search, setSearch] = useState("");
  const [progress, setProgress] = useState({ total_points: 0, challenges_completed: 0 });
  const [message, setMessage] = useState<string | null>(null);

  /** Carga el estado completo necesario para el panel del jugador. */
  const load = useCallback(async () => {
    // Carga independiente: un fallo en una fuente auxiliar no debe ocultar
    // los retos o las conexiones que sí están disponibles.
    const results = await Promise.allSettled([
      api.challenges(),
      api.ranking(),
      api.runs(),
      api.progress(),
      api.playerLaboratories(),
    ]);

    const [challengesResult, rankingResult, runsResult, progressResult, labsResult] = results;
    const errors: string[] = [];

    if (challengesResult.status === "fulfilled") {
      setChallenges(challengesResult.value);
      setSelectedCode((current) => current || challengesResult.value[0]?.code || null);
      observeAssignedChallenges(userId, challengesResult.value.map((challenge) => challenge.id));
    } else {
      errors.push("retos");
    }

    if (rankingResult.status === "fulfilled") {
      setRanking(rankingResult.value.rows);
    } else {
      errors.push("ranking");
    }

    if (runsResult.status === "fulfilled") {
      setRuns(runsResult.value);
    } else {
      errors.push("conexiones");
    }

    if (progressResult.status === "fulfilled") {
      setProgress(progressResult.value);
    } else {
      errors.push("progreso");
    }

    if (labsResult.status === "fulfilled") {
      setLaboratories(labsResult.value);
    } else {
      errors.push("laboratorios");
    }

    if (errors.length) {
      setMessage(`No se pudieron cargar: ${errors.join(", ")}.`);
    }
  }, [userId]);

  useEffect(() => {
    void load();
  }, [load]);

  useRankingLive(setRanking);

  const visibleChallenges = useMemo(() => {
    const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
    const query = normalize(search.trim());
    return challenges.filter((item) =>
      (filter === "Todas" || item.difficulty === filter) &&
      (categoryFilter === "Todas" || inferCategory(item) === categoryFilter) &&
      (!query || normalize([item.code, item.name, item.description, item.category, item.mitre_technique].join(" ")).includes(query)),
    );
  }, [challenges, filter, categoryFilter, search]);

  const selected = visibleChallenges.find((item) => item.code === selectedCode) || visibleChallenges[0] || null;

  /** Agrupa los retos para la pantalla de categorías. */
  const categories = useMemo(() => {
    const map = new Map<string, { total: number; completed: number }>();

    challenges.forEach((challenge) => {
      const key = inferCategory(challenge);
      const current = map.get(key) || { total: 0, completed: 0 };
      map.set(key, {
        total: current.total + 1,
        completed: current.completed + (challenge.completed ? 1 : 0),
      });
    });

    return map;
  }, [challenges]);

  /**
   * Inicia un reto y lleva al estudiante a su espacio de laboratorio.
   *
   * La URL de Guacamole se conserva como contingencia, pero no se abre de
   * forma automática: un enlace opaco no equivale a una sesión embebida ni
   * debe sacar al estudiante de la experiencia principal.
   */
  const start = async (code: string) => {
    try {
      const run = await api.start(code);
      setRuns((old) => [run, ...old.filter((item) => item.challenge_code !== code)]);
      setSelectedCode(code);
      setView("challenges");
      setMessage("Instancia asignada. La terminal está integrada en el reto.");
      publishNotification(userId, "lab.ready");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo iniciar el reto");
      publishNotification(userId, "lab.error");
      throw err;
    }
  };

  /** Cierra la ejecución y permite al backend limpiar la VM víctima. */
  const closeRun = async (id: number) => {
    try {
      await api.closeRun(id);
      setRuns((current) => current.filter((run) => run.id !== id));
      sessionStorage.removeItem(`ctf-laboratory-notes:${id}`);
      await load();
      setMessage("Sesión cerrada. La evidencia dinámica de la VM fue limpiada.");
      publishNotification(userId, "lab.closed");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo cerrar la sesión");
      publishNotification(userId, "lab.close_error");
      throw err;
    }
  };

  /** Envía una flag al backend y actualiza el progreso mostrado. */
  const submit = async (code: string, value: string) => {
    try {
      const result = await api.submit(code, value);
      publishNotification(userId, result.correct ? "flag.correct" : "flag.incorrect");
      await load();
      return result;
    } catch (error) {
      publishNotification(userId, "flag.error");
      throw error;
    }
  };

  return {
    view,
    setView,
    menuOpen,
    setMenuOpen,
    challenges,
    ranking,
    runs,
    laboratories,
    selectedCode,
    setSelectedCode,
    filter,
    setFilter,
    categoryFilter,
    setCategoryFilter,
    search,
    setSearch,
    progress,
    message,
    setMessage,
    selected,
    visibleChallenges,
    categories,
    load,
    start,
    closeRun,
    submit,
  };
}

/** Contrato público consumido por las vistas del jugador. */
export type PlayerController = ReturnType<typeof usePlayerController>;
