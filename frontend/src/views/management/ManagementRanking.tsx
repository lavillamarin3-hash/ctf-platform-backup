// ============================================================
// VISTA: ManagementRanking
// Responsabilidad: presentación de una sección del panel.
// ============================================================

import { createElement } from "react";
import { Ranking } from "../../components/common";
import type { ManagementController } from "../../controllers/useManagementController";

export function ManagementRanking({ controller }: { controller: ManagementController }) {
  // Estado y datos que esta vista presenta.
  const {
    user, ranking,
  } = controller;

  // Acciones proporcionadas por el controlador.
  const {
    load,
  } = controller;
  return (
<section>
    <div className="page-heading">
      <div>
        <span className="eyebrow accent">COMPETENCIA</span>
        <h1>Ranking general</h1>
        <p>Más puntos dan mejor puesto. En empate, va primero quien alcanzó esa puntuación antes. Se actualiza al completar retos.</p>
      </div>
      <div className="page-actions">
        <button className="secondary-action" onClick={() => void load()}>Actualizar</button>
      </div>
    </div>

    <div style={{ marginTop: 18 }}>
      <Ranking rows={ranking} user={user} />
    </div>
  </section>
  );
}
