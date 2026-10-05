// ============================================================
// RETOS Y FLAGS
// Responsabilidad: detalle, envío de flags y formulario de administración de retos.
// ============================================================

import { createElement, FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, Challenge, Run } from "../api";
import { difficultyStyle, categoryMeta } from "../config";
import { Icon, ErrorMessage } from "./common";
import { LaboratoryRunWorkspace } from "./player/LaboratoryRunWorkspace";
import { needsLaboratoryCleanup } from "../lib/laboratoryRunState";
import { ChallengeLearningResources } from "./ChallengeLearningResources";
import { ChallengeResource, MAX_CHALLENGE_RESOURCES, parseChallengeResources, serializeChallengeResources } from "../lib/challengeResources";
import { initialFlagTemplate } from "../lib/challengeFlagChanges";
import { challengeCategoryOptions, isValidChallengeCategory, normalizeChallengeCategory } from "../lib/challengeCategories";

export function challengeInternalLevel(
  difficulty: Challenge["difficulty"]
) {
  if (difficulty === "Básico") return 1;
  if (difficulty === "Medio") return 2;
  return 3;
}

export function ChallengeCard({
  challenge,
  selected,
  onClick,
}: {
  challenge: Challenge;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`challenge-card ${
        selected ? "selected" : ""
      }`}
      onClick={onClick}
    >
      <div className="challenge-top">
        <span className="challenge-code">
          {challenge.code}
        </span>

        <div className="challenge-top-right">
          <span className="challenge-level-badge">
            Nivel {challengeInternalLevel(challenge.difficulty)}
          </span>

          <span
            className={`difficulty ${
              difficultyStyle[
                challenge.difficulty
              ]
            }`}
          >
            {challenge.difficulty}
          </span>
        </div>
      </div>

      <h3>{challenge.name}</h3>

      <div className="challenge-category">
        {challenge.category}
      </div>

      <p>{challenge.description}</p>

      <div className="challenge-foot">
        <span>
          {
            challenge.mitre_technique.split(
              " — "
            )[0]
          }
        </span>

        <strong>
          {challenge.points} pts
        </strong>
      </div>

      {challenge.completed && (
        <span className="completed-badge">
          <Icon name="check" />
          Completado
        </span>
      )}
    </button>
  );
}

export function ChallengeDetail({
  challenge,
  runs,
  onStart,
  onSubmit,
  onClose,
}: {
  challenge: Challenge | null;
  runs: Run[];
  onStart: (code: string) => Promise<void>;
  onSubmit: (code: string, flag: string) => Promise<{
    correct: boolean;
    challenge_completed: boolean;
    awarded_points: number;
    message: string;
  }>;
  onClose: (runId: number) => Promise<void>;
}) {
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const learning = useMemo(() => parseChallengeResources(challenge?.instructions ?? ""), [challenge?.instructions]);

  useEffect(() => {
    setStarting(false);
    setStartError(null);
  }, [challenge?.code]);

  if (!challenge) {
    return (
      <div className="detail-empty">
        Selecciona uno de tus retos para leer las instrucciones y abrir su laboratorio.
      </div>
    );
  }

  const activeRun = runs.find((run) => run.challenge_code === challenge.code && needsLaboratoryCleanup(run));
  const startLaboratory = async () => {
    setStarting(true);
    setStartError(null);
    try {
      await onStart(challenge.code);
    } catch (error) {
      setStartError(error instanceof Error ? error.message : "No se pudo iniciar el laboratorio.");
    } finally {
      setStarting(false);
    }
  };

  return (
    <section className="detail-panel challenge-detail" aria-label={`Detalle del reto ${challenge.name}`}>
      <div className="detail-header">
        <div><span className="challenge-code">{challenge.code}</span><h2>{challenge.name}</h2></div>
        <span className={`difficulty ${difficultyStyle[challenge.difficulty]}`}>{challenge.difficulty}</span>
      </div>
      <p className="detail-description">{challenge.description}</p>
      <div className="challenge-summary">
        <span className="challenge-category">{challenge.category}</span>
        <span>{challenge.mitre_technique}</span>
        <strong className="accent-text">{challenge.points} pts</strong>
        {challenge.completed && <span className="completed-chip"><Icon name="check" />Completado</span>}
      </div>

      <details className="challenge-accordion" open>
        <summary><span>Objetivo e instrucciones</span><small>Guía del reto</small></summary>
        <div className="instruction-box">
          <p className="challenge-instructions">{learning.instructions || "Sigue las indicaciones del instructor para este laboratorio."}</p>
        </div>
      </details>

      <ChallengeLearningResources resources={learning.resources} topic={challenge.category} />

      {activeRun ? (
        <LaboratoryRunWorkspace key={activeRun.id} run={activeRun} onClose={onClose} onSubmit={onSubmit} />
      ) : (
        <section className="laboratory-start-panel" aria-label="Inicio de laboratorio" aria-busy={starting}>
          <div className="laboratory-start-heading">
            <div><span className="eyebrow accent">LABORATORIO</span><h3>Prepara tu espacio de práctica</h3></div>
            <span className="muted-chip">{starting ? "Preparando" : "Sin sesión activa"}</span>
          </div>
          <ol className="laboratory-flow" aria-label="Pasos del laboratorio">
            <li><span>1</span>Inicia tu instancia</li>
            <li><span>2</span>Investiga en la terminal</li>
            <li><span>3</span>Pega y valida la flag</li>
          </ol>
          <p>La terminal, el bloc de notas y el envío de flag aparecerán aquí cuando tu entorno esté listo.</p>
          {challenge.completed && <p className="practice-note">Puedes practicar de nuevo. Los puntos de este reto se otorgan una sola vez.</p>}
          <ErrorMessage message={startError} />
          <button type="button" className="primary-action" onClick={() => void startLaboratory()} disabled={starting}>
            <Icon name="play" />{starting ? "Preparando laboratorio…" : challenge.completed ? "Reabrir entorno de práctica" : "Iniciar laboratorio"}
          </button>
        </section>
      )}

      <details className="challenge-accordion">
        <summary><span>Información del escenario</span><small>Ver detalles</small></summary>
        <div className="detail-meta">
          <div><span>CATEGORÍA</span><strong>{challenge.category}</strong></div>
          <div><span>DIFICULTAD</span><strong>{challenge.difficulty}</strong></div>
          <div><span>ESCENARIO</span><strong>{challenge.scenario || "CTF general"}</strong></div>
          <div><span>ACTIVOS ASIGNADOS</span><strong>{challenge.asset_references.join(" · ") || "Definidos al iniciar"}</strong></div>
        </div>
      </details>

      <div className="hint-panel challenge-hints">
        <div className="hint-panel-head">
          <div><span className="eyebrow accent">AYUDAS DEL INSTRUCTOR</span><h3>Pistas y sugerencias</h3></div>
          <span className="hint-badge">sin revelar la flag</span>
        </div>
        {challenge.code === "LAB-01" ? (
          <div className="hint-list">
            <details><summary>Pista 1 · reconocimiento</summary><p>Identifica los servicios del objetivo asignado. Usa únicamente los activos indicados en las instrucciones de este reto.</p></details>
            <details><summary>Pista 2 · acceso</summary><p>Utiliza la terminal del laboratorio y las indicaciones del instructor para investigar el sistema.</p></details>
            <details><summary>Pista 3 · localización</summary><p>Busca los archivos destinados al ejercicio CTF. La ruta preparada para este laboratorio es <code>/opt/ctf/flag.txt</code>.</p></details>
          </div>
        ) : (
          <div className="hint-list"><details><summary>Sugerencia</summary><p>Lee el objetivo y divide el reto en pequeñas comprobaciones antes de enviar tu respuesta.</p></details></div>
        )}
      </div>
    </section>
  );
}

export function inferCategory(
  challenge: Challenge
): string {
  return (
    challenge.category ||
    "MISC"
  );
}

export function ChallengeForm({
  initial,
  onClose,
  onSave,
  laboratories = [],
  groups = [],
  categories = [],
}: {
  initial: Challenge | null;
  onClose: () => void;
  onSave: (
    challenge: Omit<Challenge, "id" | "completed" | "flag_count" | "flags">,
    flags: Array<{
      id?: number;
      label: string;
      mode: "static" | "dynamic";
      value: string;
      template: string;
      flag_order: number;
      is_active: boolean;
    }>,
    groupIds: number[]
  ) => Promise<void>;
  laboratories?: Array<{
    id: number | string;
    code?: string | null;
    name: string;
    vms?: Array<{
      id: number | string;
      name: string;
      os?: string;
      operatingSystem?: string;
    }>;
  }>;
  groups?: Array<{
    id: number;
    name: string;
    code: string;
    challenges: Array<{ challenge_id: number; code: string; name: string }>;
  }>;
  categories?: string[];
}) {
  const firstAsset = initial?.asset_references?.[0] ?? "";
  const [code, setCode] = useState(initial?.code ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [category, setCategory] = useState(initial?.category ?? "MISC");
  const [addingCategory, setAddingCategory] = useState(false);
  const [newCategory, setNewCategory] = useState("");
  const categoryOptions = useMemo(
    () => challengeCategoryOptions(Object.keys(categoryMeta), categories, category),
    [categories, category]
  );
  const [difficulty, setDifficulty] = useState<Challenge["difficulty"]>(initial?.difficulty ?? "Básico");
  const [scenario, setScenario] = useState(initial?.scenario ?? "");
  const [mitre, setMitre] = useState(initial?.mitre_technique ?? "—");
  const [assets, setAssets] = useState(initial?.asset_references?.join(", ") ?? firstAsset);
  const [primaryAsset, setPrimaryAsset] = useState(firstAsset);
  const [points, setPoints] = useState(String(initial?.points ?? 100));
  const [description, setDescription] = useState(initial?.description ?? "");
  const initialLearning = useMemo(() => parseChallengeResources(initial?.instructions ?? ""), [initial?.instructions]);
  const [instructions, setInstructions] = useState(initialLearning.instructions);
  const [resources, setResources] = useState<ChallengeResource[]>(initialLearning.resources);
  const [published, setPublished] = useState(initial?.is_published ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  type Draft = {
    id?: number;
    label: string;
    mode: "static" | "dynamic";
    value: string;
    template: string;
    flag_order: number;
    is_active: boolean;
  };

  const [flags, setFlags] = useState<Draft[]>(() =>
    initial?.flags?.map((flag) => ({
      id: flag.id,
      label: flag.label,
      mode: flag.mode ?? "static",
      value: "",
      template: initialFlagTemplate(flag, initial?.code ?? "CODE"),
      flag_order: flag.flag_order,
      is_active: flag.is_active,
    })) ?? []
  );

  const existingGroupIds = useMemo(
    () =>
      initial
        ? groups.filter((group) => group.challenges.some((item) => item.challenge_id === initial.id)).map((group) => group.id)
        : [],
    [groups, initial]
  );
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>(existingGroupIds);

  useEffect(() => {
    setSelectedGroupIds(existingGroupIds);
  }, [existingGroupIds]);

  useEffect(() => {
    if (!primaryAsset && laboratories[0]) {
      const fallback = laboratories[0].vms?.[0]?.name ?? laboratories[0].code ?? laboratories[0].name;
      setPrimaryAsset(fallback);
    }
  }, [laboratories, primaryAsset]);

  const assetOptions = useMemo(() => {
    const options: Array<{ value: string; label: string }> = [];
    laboratories.forEach((lab) => {
      const labValue = lab.code || lab.name;
      options.push({ value: labValue, label: `${labValue} · ${lab.name}` });
      (lab.vms ?? []).forEach((vm) => {
        options.push({ value: vm.name, label: `${vm.name} · ${vm.os || vm.operatingSystem || "VM"}` });
      });
    });
    return options;
  }, [laboratories]);

  const addFlag = () =>
    setFlags((current) => [
      ...current,
      {
        label: `Flag ${current.length + 1}`,
        mode: "static",
        value: "",
        template: "FLAG{ssh_{{USER}}_{{RUN_ID}}_{{RAND}}}",
        flag_order: current.length + 1,
        is_active: true,
      },
    ]);

  const updateFlag = (index: number, patch: Partial<Draft>) =>
    setFlags((current) => current.map((flag, i) => (i === index ? { ...flag, ...patch } : flag)));

  const toggleGroup = (groupId: number) =>
    setSelectedGroupIds((current) =>
      current.includes(groupId) ? current.filter((id) => id !== groupId) : [...current, groupId]
    );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const selectedCategory = addingCategory ? normalizeChallengeCategory(newCategory) : category;
      if (!isValidChallengeCategory(selectedCategory)) {
        throw new Error("La categoría debe tener entre 2 y 48 caracteres: letras, números, espacios, /, _ o -.");
      }
      const references = [primaryAsset, ...assets.split(",").map((value) => value.trim()).filter(Boolean)];
      const uniqueReferences = [...new Set(references.filter(Boolean))];
      if (!uniqueReferences.length) throw new Error("Selecciona al menos un laboratorio o una VM.");
      await onSave(
        {
          code: code.trim().toUpperCase(),
          name: name.trim(),
          category: selectedCategory,
          difficulty,
          scenario: scenario || null,
          mitre_technique: mitre || "—",
          asset_references: uniqueReferences,
          points: Number(points),
          description: description.trim(),
          instructions: serializeChallengeResources(instructions, resources),
          is_published: published,
        },
        flags,
        selectedGroupIds
      );
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el reto");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <form className="modal-card challenge-modal" onSubmit={submit}>
        <div className="modal-head">
          <div>
            <span className="eyebrow accent">GESTIÓN DE RETO</span>
            <h2>{initial ? `Editar ${initial.code}` : "Nuevo reto"}</h2>
            <small>Relaciona el reto con un laboratorio real, grupos de estudiantes y sus flags.</small>
          </div>
          <button type="button" className="icon-btn" onClick={onClose}>×</button>
        </div>

        {error && <ErrorMessage message={error} />}

        <div className="form-grid">
          <label>Código<input value={code} onChange={(event) => setCode(event.target.value)} disabled={Boolean(initial)} required /></label>
          <label>Nombre<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
          <label>Categoría
            <select value={addingCategory ? "__new__" : category} onChange={(event) => {
              if (event.target.value === "__new__") {
                setAddingCategory(true);
                setNewCategory("");
              } else {
                setAddingCategory(false);
                setCategory(event.target.value);
              }
            }}>
              {categoryOptions.map((value) => <option key={value} value={value}>{value}</option>)}
              <option value="__new__">+ Nueva categoría…</option>
            </select>
          </label>
          {addingCategory && <label>Nueva categoría
            <input value={newCategory} onChange={(event) => setNewCategory(event.target.value)} maxLength={48} required placeholder="Ej.: REDES Y DEFENSA" />
            <small className="field-help">Se guardará al crear o editar este reto y luego aparecerá en la lista.</small>
          </label>}
          <label>Dificultad<select value={difficulty} onChange={(event) => setDifficulty(event.target.value as Challenge["difficulty"])}><option>Básico</option><option>Medio</option><option>Avanzado</option></select></label>
          <label>Escenario<input value={scenario} onChange={(event) => setScenario(event.target.value)} /></label>
          <label>MITRE<input value={mitre} onChange={(event) => setMitre(event.target.value)} /></label>
          <label>Laboratorio / VM
            <select value={primaryAsset} onChange={(event) => setPrimaryAsset(event.target.value)} required>
              <option value="">Selecciona un activo…</option>
              {assetOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <small className="field-help">La VM seleccionada determina IP, protocolo y conexión Guacamole cuando el jugador inicia el reto.</small>
          </label>
          <label>Puntos<input type="number" min="1" max="10000" value={points} onChange={(event) => setPoints(event.target.value)} required /></label>
        </div>

        <label className="form-full">Activos adicionales
          <input value={assets} onChange={(event) => setAssets(event.target.value)} placeholder="LAB-LNXVICT, otra-vm" />
          <small className="field-help">Opcional. Usa nombres exactos separados por comas.</small>
        </label>
        <label className="form-full">Descripción<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} required /></label>
        <label className="form-full">Instrucciones del reto<textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} rows={4} /></label>

        <section className="learning-resource-editor">
          <div className="panel-head">
            <div><span className="eyebrow accent">MATERIAL POR TEMA</span><h3>Videos y presentaciones</h3><p>Asocia material de apoyo a este reto. Usa enlaces HTTPS o rutas de archivos alojados en la plataforma.</p></div>
            <button type="button" className="secondary-action" disabled={resources.length >= MAX_CHALLENGE_RESOURCES} onClick={() => setResources((current) => [...current, { kind: "video", title: "", url: "" }])}>+ Añadir recurso</button>
          </div>
          {resources.map((resource, index) => (
            <div className="learning-resource-editor-row" key={index}>
              <div className="resource-editor-head"><strong>Recurso {index + 1}</strong><button type="button" className="table-action danger" onClick={() => setResources((current) => current.filter((_, itemIndex) => itemIndex !== index))}>Quitar recurso</button></div>
              <div className="form-grid">
                <label>Tipo de recurso<select value={resource.kind} onChange={(event) => setResources((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, kind: event.target.value as ChallengeResource["kind"] } : item))}><option value="video">Video</option><option value="presentation">Presentación</option></select></label>
                <label>Título<input value={resource.title} maxLength={180} required onChange={(event) => setResources((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item))} placeholder="Introducción al tema" /></label>
                <label className="form-span-2">URL del recurso<input value={resource.url} required maxLength={2048} onChange={(event) => setResources((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, url: event.target.value } : item))} placeholder="https://… o /media/material.pdf" /></label>
              </div>
            </div>
          ))}
          {!resources.length && <p className="resource-editor-empty">Añade un video explicativo o una presentación para acompañar las instrucciones.</p>}
          <small className="field-help">Los videos de YouTube y los archivos MP4/WebM/OGG se reproducen dentro del reto. Las presentaciones se abren en su visor de origen. Máximo {MAX_CHALLENGE_RESOURCES} recursos.</small>
        </section>

        <section className="glass-panel flag-builder">
          <div className="panel-head">
            <div><span className="eyebrow accent">FLAGS</span><h3>Validación del reto</h3><small>Las flags dinámicas se generan por ejecución, se inyectan en la VM víctima y solo se valida su hash asociado a esa ejecución.</small></div>
            <button type="button" className="secondary-action" onClick={addFlag}>+ Añadir flag</button>
          </div>
          {flags.map((flag, index) => (
            <div className="flag-builder-row" key={flag.id ?? `new-${index}`}>
              <div className="flag-builder-head"><strong>Flag {flag.flag_order}</strong><button type="button" className="table-action danger" onClick={() => setFlags((current) => current.filter((_, i) => i !== index))}>Eliminar</button></div>
              <div className="form-grid">
                <label>Etiqueta<input value={flag.label} onChange={(event) => updateFlag(index, { label: event.target.value })} /></label>
                <label>Tipo<select value={flag.mode} onChange={(event) => updateFlag(index, { mode: event.target.value as Draft["mode"] })}><option value="static">Estática</option><option value="dynamic">Dinámica por ejecución</option></select></label>
                {flag.mode === "static" ? (
                  <div className="form-span-2 static-flag-guidance">
                    <label>Valor<input type="password" autoComplete="new-password" value={flag.value} onChange={(event) => updateFlag(index, { value: event.target.value })} placeholder={flag.id ? "Deja vacío para conservar el valor existente" : "FLAG{valor_estatico}"} /></label>
                    <small className="field-help">El backend no devuelve el valor existente; al guardar se registra únicamente el hash. Coloca el mismo valor manualmente en la VM o artefacto. No se inyecta ni se borra al cerrar una corrida. Usa una ruta exclusiva, distinta de la flag dinámica de LAB-01.</small>
                  </div>
                ) : (
                  <label className="form-span-2">Plantilla<input value={flag.template} onChange={(event) => updateFlag(index, { template: event.target.value })} /><small className="field-help">Variables: {'{{CODE}}'}, {'{{USER}}'}, {'{{RUN_ID}}'}, {'{{RAND}}'}</small></label>
                )}
                <label>Orden<input type="number" min="1" max="10" value={flag.flag_order} onChange={(event) => updateFlag(index, { flag_order: Number(event.target.value) })} /></label>
              </div>
              <label className="switch-row"><input type="checkbox" checked={flag.is_active} onChange={(event) => updateFlag(index, { is_active: event.target.checked })} /><span>Flag activa</span></label>
            </div>
          ))}
          {!flags.length && <div className="empty-card"><strong>No hay flags configuradas</strong><span>Añade una flag para poder iniciar el reto.</span></div>}
        </section>

        <section className="glass-panel assignment-panel">
          <div className="panel-head"><div><span className="eyebrow accent">GRUPOS</span><h3>Publicación por grupo</h3><small>Solo los estudiantes de los grupos seleccionados verán este reto.</small></div></div>
          <div className="selection-list">
            {groups.map((group) => (
              <label className="selection-row" key={group.id}>
                <input type="checkbox" checked={selectedGroupIds.includes(group.id)} onChange={() => toggleGroup(group.id)} />
                <span><strong>{group.code}</strong><small className="table-subline">{group.name} · {group.challenges.length} retos asignados</small></span>
              </label>
            ))}
          </div>
          {!groups.length && <div className="empty-card"><strong>No hay grupos</strong><span>Crea primero un grupo de estudiantes.</span></div>}
        </section>

        <label className="switch-row"><input type="checkbox" checked={published} onChange={(event) => setPublished(event.target.checked)} /><span>Publicar reto inmediatamente</span></label>
        <div className="modal-actions"><button type="button" className="secondary-action" onClick={onClose}>Cancelar</button><button className="primary-action" disabled={busy}>{busy ? "Guardando…" : initial ? "Guardar cambios" : "Crear reto"}</button></div>
      </form>
    </div>
  );
}
