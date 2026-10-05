// ============================================================
// PANEL DE INVITADO
// Responsabilidad: catálogo público y consulta en modo lectura.
// ============================================================

import { createElement, FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, Challenge, RankingRow, User } from "../api";
import { Theme, ThemePreference, ManagementView } from "../config";
import { GuestSidebar, Header, StatCard, Ranking } from "../components/common";
import { ChallengeCard, inferCategory } from "../components/challenges";
import { useRankingLive } from "../lib/useRankingLive";

export function GuestApp({
  user,
  onLogout,
  theme,
  onToggleTheme,
  themePreference,
  onThemePreferenceChange,
  onUserChange,
}: {
  user: User;
  onLogout: () => void;
  theme: Theme;
  onToggleTheme: () => void;
  themePreference: ThemePreference;
  onThemePreferenceChange: (value: ThemePreference) => void;
  onUserChange: (user: User) => void;
}) {
  const [view, setView] =
    useState<ManagementView>(
      "dashboard"
    );

  const [menuOpen, setMenuOpen] =
    useState(false);

  const [challenges, setChallenges] =
    useState<Challenge[]>([]);

  const [ranking, setRanking] =
    useState<RankingRow[]>([]);

  useRankingLive(setRanking);

  const [selected, setSelected] =
    useState<string | null>(
      null
    );

  useEffect(() => {
    Promise.all([
      api.challenges(),
      api.ranking(),
    ])
      .then(([c, r]) => {
        setChallenges(c);
        setRanking(r.rows);

        if (c[0]) {
          setSelected(
            c[0].code
          );
        }
      })
      .catch(() => {
        // vista pública
      });
  }, []);

  const challenge =
    challenges.find(
      (c) =>
        c.code ===
        selected
    ) || null;

  return (
    <div className="app-shell">
      <GuestSidebar
        view={view}
        setView={setView}
        open={menuOpen}
        onClose={() =>
          setMenuOpen(false)
        }
      />

      <div className="page-shell">
        <Header
          user={user}
          roleLabel="Invitado · Solo lectura"
          onLogout={onLogout}
          onOpenMenu={() =>
            setMenuOpen(true)
          }
          theme={theme}
          onToggleTheme={
            onToggleTheme
          }
          themePreference={themePreference}
          onThemePreferenceChange={onThemePreferenceChange}
          onUserChange={onUserChange}
        />

        <main className="main-content">
          {view ===
            "dashboard" && (
            <>
              <section className="hero">
                <div>
                  <span className="eyebrow accent">
                    CONSULTA
                  </span>

                  <h1>
                    Bienvenido al{" "}
                    <em>
                      laboratorio
                    </em>
                  </h1>

                  <p>
                    Vista pública de la plataforma.
                    El acceso al laboratorio está
                    reservado para jugadores autorizados.
                  </p>
                </div>

                <div className="level-badge">
                  <span>
                    RETOS
                  </span>

                  <strong>
                    {
                      challenges.length
                    }
                  </strong>
                </div>
              </section>

              <section className="stats-grid">
                <StatCard
                  label="Retos publicados"
                  value={
                    challenges.length
                  }
                  helper="Consulta pública"
                  icon="flag"
                  accent="purple"
                />

                <StatCard
                  label="Ranking"
                  value={
                    ranking.length
                  }
                  helper="Jugadores visibles"
                  icon="trophy"
                  accent="blue"
                />

                <StatCard
                  label="Laboratorio"
                  value="RESTRINGIDO"
                  helper="Solo jugadores"
                  icon="lock"
                  accent="red"
                />

                <StatCard
                  label="Modo"
                  value="LECTURA"
                  helper="Sin envío de flags"
                  icon="chart"
                  accent="cyan"
                />
              </section>

              <div className="dashboard-grid">
                <div className="glass-panel info-panel">
                  <span className="eyebrow">
                    ACCESO
                  </span>

                  <h2>
                    Explora el catálogo
                  </h2>

                  <p>
                    Consulta los retos y su dificultad.
                    Para abrir laboratorios o enviar
                    flags debes utilizar una cuenta de
                    jugador autorizada.
                  </p>

                  <button
                    className="primary-action"
                    onClick={() =>
                      setView(
                        "challenges"
                      )
                    }
                  >
                    Ver retos
                  </button>
                </div>

                <Ranking
                  rows={ranking}
                  user={user}
                />
              </div>
            </>
          )}

          {view ===
            "challenges" && (
            <section>
              <div className="page-heading">
                <div>
                  <span className="eyebrow accent">
                    CATÁLOGO PÚBLICO
                  </span>

                  <h1>
                    Retos
                  </h1>

                  <p>
                    Vista de consulta. Las instrucciones
                    de acceso al laboratorio permanecen
                    restringidas.
                  </p>
                </div>
              </div>

              <div className="challenge-layout">
                <div className="challenge-list">
                  {challenges.map(
                    (c) => (
                      <ChallengeCard
                        key={c.id}
                        challenge={c}
                        selected={
                          c.code ===
                          selected
                        }
                        onClick={() =>
                          setSelected(
                            c.code
                          )
                        }
                      />
                    )
                  )}
                </div>

                <div className="detail-panel">
                  <span className="eyebrow">
                    DETALLE
                  </span>

                  {challenge ? (
                    <>
                      <h2>
                        {
                          challenge.name
                        }
                      </h2>

                      <p className="detail-description">
                        {
                          challenge.description
                        }
                      </p>

                      <div className="detail-meta">
                        <div>
                          <span>
                            CATEGORÍA
                          </span>

                          <strong>
                            {inferCategory(
                              challenge
                            )}
                          </strong>
                        </div>

                        <div>
                          <span>
                            DIFICULTAD
                          </span>

                          <strong>
                            {
                              challenge.difficulty
                            }
                          </strong>
                        </div>

                        <div>
                          <span>
                            PUNTOS
                          </span>

                          <strong>
                            {
                              challenge.points
                            }
                          </strong>
                        </div>
                      </div>

                      <div className="instruction-box">
                        <span>
                          ACCESO RESTRINGIDO
                        </span>

                        <p>
                          El laboratorio y el envío de
                          flags están disponibles únicamente
                          para jugadores autorizados.
                        </p>
                      </div>
                    </>
                  ) : (
                    <p className="empty-text">
                      Selecciona un reto para consultar
                      su información pública.
                    </p>
                  )}
                </div>
              </div>
            </section>
          )}

          {view ===
            "ranking" && (
            <section>
              <div className="page-heading">
                <div>
                  <span className="eyebrow accent">
                    CLASIFICACIÓN
                  </span>

                  <h1>
                    Ranking
                  </h1>

                  <p>
                    Clasificación pública de la actividad
                    CTF.
                  </p>
                </div>
              </div>

              <Ranking
                rows={ranking}
                user={user}
              />
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
