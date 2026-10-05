// ============================================================
// CONTROLADOR DEL PANEL DE GESTIÓN
// Responsabilidad: estado, carga de datos y acciones.
// No contiene JSX. Las vistas consumen este contrato.
// ============================================================

import { useCallback, useEffect, useMemo, useState } from "react";

import { api, Challenge, RankingRow, User } from "../api";
import {
  ManagementView,
  ManagedUser,
  UserFunction,
  Laboratory,
  LabVM,
} from "../config";
import { mapBackendLaboratory, mapBackendVM } from "../components/laboratory";
import { FlagDraft, hasFlagDraftChanges } from "../lib/challengeFlagChanges";
import { useRankingLive } from "../lib/useRankingLive";
import { BEGINNER_CHALLENGE_DRAFTS, isLegacyReconDraft, legacyPublishedCodes } from "../lib/pilotChallenges";

const defaultUserFunction = (role: User["role"]): UserFunction =>
  role === "admin"
    ? "Administrador de laboratorio"
    : role === "instructor"
      ? "Instructor"
      : role === "player"
        ? "Estudiante"
        : "Otro";

/** Normaliza datos de usuario para evitar valores vacíos en las vistas. */
const normalizeManagedUser = (
  item: User,
  fallback: Partial<Pick<ManagedUser, "full_name" | "user_function" | "organization">> = {},
): ManagedUser => ({
  ...item,
  full_name: item.full_name?.trim() || fallback.full_name?.trim() || item.username,
  user_function:
    (item.user_function as UserFunction) ||
    fallback.user_function ||
    defaultUserFunction(item.role),
  organization:
    item.organization?.trim() ||
    fallback.organization?.trim() ||
    "Sin organización",
  demo: (item as ManagedUser).demo,
});

export function useManagementController({
  user,
  panelRole,
}: {
  user: User;
  panelRole: "admin" | "instructor";
}) {
  const [view, setView] =
    useState<ManagementView>(
      "dashboard"
    );

  const [menuOpen, setMenuOpen] =
    useState(false);

  const [challenges, setChallenges] =
    useState<Challenge[]>([]);

  const [catalogActionBusy, setCatalogActionBusy] = useState(false);

  const [users, setUsers] =
    useState<ManagedUser[]>([]);

  const [userSearch, setUserSearch] =
    useState("");

  const [userRoleFilter, setUserRoleFilter] =
    useState<"Todas" | User["role"]>("Todas");

  const [userFormOpen, setUserFormOpen] =
    useState(false);

  const [userEditing, setUserEditing] =
    useState<ManagedUser | null>(null);

  const [ranking, setRanking] =
    useState<RankingRow[]>([]);

  useRankingLive(setRanking);

  const [groups, setGroups] =
    useState<import("../api").StudentGroup[]>([]);

  const [progressRows, setProgressRows] =
    useState<import("../api").ProgressRow[]>([]);

  const [message, setMessage] =
    useState<string | null>(
      null
    );

  const [editing, setEditing] =
    useState<Challenge | null>(
      null
    );

  const [creating, setCreating] =
    useState(false);

  /* ---------------- LABORATORIOS ---------------- */

  // El inventario administrativo debe provenir del servidor. Un respaldo
  // local puede aparentar VMs operativas que no existen en PostgreSQL.
  const [laboratories, setLaboratories] = useState<Laboratory[]>([]);
  const [laboratoryError, setLaboratoryError] = useState<string | null>(null);

  const [selectedLabId, setSelectedLabId] = useState<string | null>(null);

  const [labFormOpen, setLabFormOpen] =
    useState(false);

  const [labEditing, setLabEditing] =
    useState<Laboratory | null>(
      null
    );

  const [vmFormOpen, setVmFormOpen] =
    useState(false);

  const [vmEditing, setVmEditing] =
    useState<LabVM | null>(
      null
    );

  /* ---------------- GUACAMOLE ---------------- */

  const [guacamoleConnections, setGuacamoleConnections] =
    useState<import("../api").GuacamoleConnection[]>([]);

  const [guacamoleMode, setGuacamoleMode] =
    useState<"stub" | "real">("stub");

  const [guacamoleServiceAccount, setGuacamoleServiceAccount] =
    useState("");

  const [guacamoleServicePassword, setGuacamoleServicePassword] =
    useState("");

  const [guacamoleTested, setGuacamoleTested] =
    useState(false);

  const [guacamoleStatus, setGuacamoleStatus] =
    useState<import("../api").GuacamoleStatus | null>(null);

  const [guacamoleUsers, setGuacamoleUsers] =
    useState<import("../api").GuacamoleUser[]>([]);

  const [guacamoleLoading, setGuacamoleLoading] =
    useState(false);

  const [guacamoleFormOpen, setGuacamoleFormOpen] = useState(false);
  const [guacamoleUserEditing, setGuacamoleUserEditing] = useState<import("../api").GuacamoleUser | null>(null);
  const [guacamoleConnectionEditing, setGuacamoleConnectionEditing] = useState<import("../api").GuacamoleConnection | null>(null);
  const [guacamoleConnectionFormOpen, setGuacamoleConnectionFormOpen] = useState(false);
  const [guacamolePermissionsUser, setGuacamolePermissionsUser] = useState<string | null>(null);
  const [guacamolePermissions, setGuacamolePermissions] = useState<import("../api").GuacamolePermissionSet>({ system_permissions: [], connection_permissions: {} });
  const [guacamolePermissionsOpen, setGuacamolePermissionsOpen] = useState(false);



  const selectedLab =
    laboratories.find(
      (lab) =>
        lab.id ===
        selectedLabId
    ) ?? null;

  const isAdmin = panelRole === "admin";

  const loadGuacamole = useCallback(async () => {
    if (!isAdmin) return;
    setGuacamoleLoading(true);
    try {
      const [statusData, usersData, connectionData] = await Promise.all([
        api.guacamoleStatus(),
        api.guacamoleUsers(),
        api.guacamoleConnections(),
      ]);
      setGuacamoleStatus(statusData);
      setGuacamoleUsers(usersData);
      setGuacamoleConnections(connectionData);
      setGuacamoleMode(statusData.mode === "real" ? "real" : "stub");
      setGuacamoleTested(true);
      setMessage("Conexión con Guacamole verificada correctamente.");
    } catch (err) {
      setGuacamoleTested(false);
      setMessage(err instanceof Error ? err.message : "No se pudo consultar Guacamole");
    } finally {
      setGuacamoleLoading(false);
    }
  }, [isAdmin]);

  /**
   * Obtiene la única conexión READ que el estudiante tiene asignada.
   * Si por una configuración anterior existen varias, se toma la
   * primera; el guardado posterior corrige la situación y deja solo una.
   */
  const loadStudentConnection = useCallback(
    async (username: string): Promise<string | null> => {
      const permissionSet =
        await api.guacamolePermissions(username);

      const assigned = Object.entries(
        permissionSet.connection_permissions || {}
      ).find(([, permissions]) =>
        permissions.includes("READ")
      );

      return assigned?.[0] ?? null;
    },
    []
  );

  /**
   * Reemplaza los permisos directos de conexión del estudiante
   * para dejar como máximo una conexión con permiso READ.
   */
  const saveStudentConnection = useCallback(
    async (
      username: string,
      connectionId: string | null
    ) => {
      if (!isAdmin) return;

      await api.setStudentConnection(
        username,
        connectionId
      );

      setMessage(
        connectionId
          ? `Conexión asignada a ${username}. Solo dispone de READ sobre la conexión seleccionada.`
          : `Se retiró la conexión directa de ${username}.`
      );
    },
    [isAdmin]
  );

  const saveGuacamoleUser = async (input: { username: string; password?: string; email?: string | null; full_name?: string | null; disabled?: boolean }, initialUsername?: string) => {
    if (!isAdmin) return;
    try {
      if (initialUsername) {
        await api.updateGuacamoleUser(initialUsername, { password: input.password, email: input.email, full_name: input.full_name, disabled: input.disabled });
        setMessage("Usuario de Guacamole actualizado correctamente.");
      } else {
        await api.createGuacamoleUser({ username: input.username, password: input.password || "", email: input.email, full_name: input.full_name });
        setMessage("Usuario creado directamente en Guacamole.");
      }
      await loadGuacamole();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo actualizar Guacamole.");
    }
  };

  const deleteGuacamoleManagedUser = async (target: import("../api").GuacamoleUser) => {
    if (!isAdmin) return;
    if (users.some((item) => item.username.toLowerCase() === target.username.toLowerCase())) {
      setView("users");
      setMessage("Esta cuenta también existe en CTF. Gestiona su acceso desde Usuarios y roles; el historial de retos se conserva.");
      return;
    }
    if (!window.confirm(`¿Eliminar ${target.username} de Guacamole?`)) return;
    try { await api.deleteGuacamoleUser(target.username); await loadGuacamole(); setMessage("Usuario eliminado de Guacamole."); } catch (err) { setMessage(err instanceof Error ? err.message : "No se pudo eliminar el usuario remoto."); }
  };

  const saveGuacamoleConnection = async (input: { name:string; protocol:"ssh"|"rdp"|"vnc"; hostname:string; port:number; username?:string|null; password?:string|null; domain?:string|null; parent_identifier?:string }, identifier?:string) => {
    if (!isAdmin) return;
    try {
      if (identifier) await api.updateGuacamoleConnection(identifier, input);
      else await api.createGuacamoleConnection(input);
      await loadGuacamole();
      setMessage(identifier ? "Conexión de Guacamole actualizada correctamente." : "Conexión de Guacamole creada correctamente.");
    } catch (err) { setMessage(err instanceof Error ? err.message : "No se pudo guardar la conexión."); }
  };
  const deleteGuacamoleManagedConnection = async (connection: import("../api").GuacamoleConnection) => {
    if (!isAdmin) return;
    if (!window.confirm(`¿Eliminar la conexión ${connection.name}?`)) return;
    try { await api.deleteGuacamoleConnection(connection.identifier); await loadGuacamole(); setMessage("Conexión eliminada correctamente."); } catch (err) { setMessage(err instanceof Error ? err.message : "No se pudo eliminar la conexión."); }
  };
  const openGuacamolePermissions = async (username:string) => {
    try { const data = await api.guacamolePermissions(username); setGuacamolePermissions(data); setGuacamolePermissionsUser(username); setGuacamolePermissionsOpen(true); } catch (err) { setMessage(err instanceof Error ? err.message : "No se pudieron consultar los permisos."); }
  };
  const saveGuacamolePermissions = async (value: import("../api").GuacamolePermissionSet) => {
    if (!guacamolePermissionsUser) return;
    try { await api.updateGuacamolePermissions(guacamolePermissionsUser, value); setGuacamolePermissions(value); setGuacamolePermissionsOpen(false); setMessage("Permisos de Guacamole actualizados correctamente."); } catch (err) { setMessage(err instanceof Error ? err.message : "No se pudieron guardar los permisos."); }
  };


  const load = useCallback(
    async () => {
      try {
        const [
          challengeData,
          rank,
        ] = await Promise.all([
          api.challenges(),
          api.ranking(),
        ]);

        setChallenges(
          challengeData
        );

        setRanking(
          rank.rows
        );

        try {
          setGroups(await api.groups());
        } catch {
          setGroups([]);
        }

        if (isAdmin || panelRole === "instructor") {
          try {
            setProgressRows(await api.progressReport());
          } catch {
            setProgressRows([]);
          }
        }

      } catch (err) {
        setMessage(
          err instanceof Error
            ? err.message
            : "No se pudo cargar el panel"
        );
      }

      // El inventario se consulta incluso si falló la carga de retos/ranking;
      // nunca debe quedar una copia local o una respuesta anterior aparentando
      // ser el estado actual de PostgreSQL.
      try {
        const backendLabs = await api.laboratories();
        const mappedLabs = backendLabs.map(mapBackendLaboratory);
        setLaboratories(mappedLabs);
        setLaboratoryError(null);
        setSelectedLabId((current) =>
          mappedLabs.some((item) => item.id === current)
            ? current
            : mappedLabs[0]?.id ?? null
        );
      } catch {
        setLaboratories([]);
        setSelectedLabId(null);
        setLaboratoryError("No se pudo consultar el inventario real. No se muestran datos locales ni se permiten cambios hasta reconectar con la API.");
      }

      try {
        const backendUsers =
          await api.visibleUsers();

        const normalized: ManagedUser[] = backendUsers.map((item) =>
          normalizeManagedUser(item, {
            full_name: item.username,
            organization: "Cyber Lab",
          })
        );

        setUsers(normalized);
      } catch (err) {
        setUsers([]);
        setMessage(
          err instanceof Error
            ? err.message
            : "No se pudieron cargar los usuarios reales."
        );
      }
    },
    [isAdmin, panelRole]
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (view === "groups") {
      void api.groups().then(setGroups).catch(() => setGroups([]));
    }
    if (view === "monitoring") {
      void api.progressReport().then(setProgressRows).catch(() => setProgressRows([]));
    }
  }, [view]);


  useEffect(() => {
    if ((view === "guacamole" || view === "laboratory") && isAdmin) {
      void loadGuacamole();
    }
  }, [view, isAdmin, loadGuacamole]);

  const published =
    challenges.filter(
      (c) =>
        c.is_published
    ).length;

  const draft =
    challenges.length -
    published;

  const points =
    challenges.reduce(
      (sum, c) =>
        sum + c.points,
      0
    );

  const activeUsers =
    users.filter(
      (u) =>
        u.is_active
    ).length;

  const roleLabel = isAdmin
    ? "Administrador"
    : "Instructor / Diseñador";

  /**
   * Persiste el reto, sus flags y las asignaciones a grupos.
   * Mantener esta función como orquestador evita mezclar llamadas de API
   * dentro de los formularios visuales.
   */
  const saveChallenge = async (input: Omit<Challenge,"id"|"completed"|"flag_count"|"flags">, draftFlags: FlagDraft[], groupIds: number[] = []) => {
    let saved: Challenge;
    if (editing) saved = await api.updateChallenge(editing.code, input);
    else saved = await api.createChallenge(input);
    const existing = editing?.flags ?? [];
    for (const flag of existing) {
      if (!draftFlags.some(f => f.id === flag.id)) await api.deleteFlag(saved.code, flag.id);
    }
    for (const flag of draftFlags) {
      const payload = { label: flag.label.trim(), value: flag.mode === "static" ? (flag.value.trim() || undefined) : undefined, flag_order: flag.flag_order, is_active: flag.is_active, mode: flag.mode, template: flag.mode === "dynamic" ? flag.template.trim() : undefined };
      if (flag.id) {
        const original = existing.find((item) => item.id === flag.id);
        if (hasFlagDraftChanges(original, flag, editing?.code ?? saved.code)) {
          await api.updateFlag(saved.code, flag.id, payload);
        }
      }
      else await api.createFlag(saved.code, payload);
    }
    const desired = new Set(groupIds);
    const assigned = groups.filter((g) => g.challenges.some((c) => c.challenge_id === saved.id)).map((g) => g.id);
    for (const groupId of desired) {
      if (!assigned.includes(groupId)) await api.assignChallengeGroup(saved.code, groupId);
    }
    for (const groupId of assigned) {
      if (!desired.has(groupId)) await api.unassignChallengeGroup(saved.code, groupId);
    }
    await load();
    setMessage(editing ? "Reto actualizado correctamente" : "Reto creado correctamente");
  };

  const archive = async (
    code: string
  ) => {
    if (
      !window.confirm(
        `¿Desactivar el reto ${code}? Se conservarán sus registros.`
      )
    ) {
      return;
    }

    try {
      await api.archiveChallenge(
        code
      );

      await load();

      setMessage(
        "Reto desactivado y conservado en el historial."
      );
    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : "No se pudo desactivar el reto"
      );
    }
  };

  const archiveLegacyChallenges = async () => {
    if (!isAdmin || catalogActionBusy) return;
    const codes = legacyPublishedCodes(challenges);
    if (!codes.length) {
      setMessage("No hay retos anteriores publicados que desactivar.");
      return;
    }
    if (!window.confirm(`Se desactivarán ${codes.length} retos y se conservarán sus resultados. LAB-01 seguirá publicado. Cierra primero todas las corridas activas.\n\n${codes.join(", ")}\n\n¿Continuar?`)) return;
    setCatalogActionBusy(true);
    const archived: string[] = [];
    const failed: string[] = [];
    try {
      for (const code of codes) {
        try {
          await api.archiveChallenge(code);
          archived.push(code);
        } catch {
          failed.push(code);
        }
      }
      await load();
      setMessage(`${archived.length} retos desactivados sin borrar historial.${failed.length ? ` No se modificaron: ${failed.join(", ")}. Cierra sus corridas activas y reintenta.` : ""}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo actualizar el catálogo.");
    } finally {
      setCatalogActionBusy(false);
    }
  };

  const createBeginnerChallengeDrafts = async () => {
    if (!isAdmin || catalogActionBusy) return;
    if (!window.confirm("Se crearán tres retos básicos con flags dinámicas como borradores sin asignaciones: dos en la VM Linux y uno Kali → Linux. Antes de publicar, comprueba acceso, servicio didáctico, inyección y limpieza reales. ¿Continuar?")) return;
    setCatalogActionBusy(true);
    const created: string[] = [];
    const updated: string[] = [];
    const skipped: string[] = [];
    const failed: string[] = [];
    try {
      for (const item of BEGINNER_CHALLENGE_DRAFTS) {
        const code = item.challenge.code;
        const existing = challenges.find((challenge) => challenge.code === code);
        if (existing && isLegacyReconDraft(existing)) {
          try {
            await api.updateChallenge(code, item.challenge);
            updated.push(code);
          } catch {
            failed.push(code);
          }
          continue;
        }
        if (existing) {
          skipped.push(code);
          continue;
        }
        try {
          await api.createChallenge(item.challenge);
          await api.createFlag(code, item.flag);
          created.push(code);
        } catch {
          failed.push(code);
        }
      }
      await load();
      setMessage(`${created.length} borradores dinámicos creados; ${updated.length} borrador legado adaptado; ${skipped.length} ya existían.${failed.length ? ` Revisa manualmente: ${failed.join(", ")}.` : ""} Ninguno se publicó ni asignó automáticamente.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo actualizar el catálogo.");
    } finally {
      setCatalogActionBusy(false);
    }
  };

  const changeUser = async (
    id: number,
    changes: Partial<
      Pick<
        User,
        "role" | "is_active" | "full_name" | "organization" | "user_function"
      >
    >
  ) => {
    if (!isAdmin) {
      return;
    }

    const target = users.find(
      (item) => item.id === id
    );

    if (!target) return;

    if (target.demo) {
      setUsers((current) =>
        current.map((item) =>
          item.id === id
            ? normalizeManagedUser({ ...item, ...changes })
            : item
        )
      );

      setMessage(
        "Usuario de demostración actualizado localmente."
      );
      return;
    }

    try {
      const updated = await api.updateUser(id, changes);
      setUsers((current) =>
        current.map((item) =>
          item.id === id ? normalizeManagedUser(updated) : item
        )
      );

      setMessage(
        "Usuario actualizado correctamente"
      );
    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : "No se pudo actualizar el usuario"
      );
    }
  };

  /**
   * Guarda un usuario real en CTF y sincroniza su cuenta de Guacamole.
   * El cierre del formulario debe ocurrir solo después del éxito.
   */
  const saveManagedUser = async (input: ManagedUser, password: string) => {
    if (!isAdmin) return;

    if (userEditing) {
      if (userEditing.demo) {
        setUsers((current) => current.map((item) => item.id === userEditing.id ? input : item));
        setMessage("Usuario de demostración actualizado localmente.");
        return;
      }
      try {
        const updated = await api.updateUser(userEditing.id, {
          role: input.role,
          is_active: input.is_active,
          full_name: input.full_name,
          organization: input.organization,
          user_function: input.user_function,
        });
        setUsers((current) => current.map((item) => item.id === userEditing.id ? normalizeManagedUser(updated, input) : item));
        setMessage("Usuario actualizado y sincronizado con Guacamole.");
        void loadGuacamole();
      } catch (err) {
        throw err;
      }
      return;
    }

    try {
      const created = await api.createUser({
        username: input.username,
        email: input.email,
        password,
        role: input.role,
        full_name: input.full_name,
        organization: input.organization,
        user_function: input.user_function,
        sync_guacamole: true,
      });
      setUsers((current) => [
        normalizeManagedUser(created, input),
        ...current.filter((item) => item.username.toLowerCase() !== created.username.toLowerCase()),
      ]);
      setMessage("Usuario creado en CTF y sincronizado con Guacamole.");
      void loadGuacamole();
    } catch (err) {
      throw err;
    }
  };

  const deleteManagedUser = async (target: ManagedUser) => {
    if (!isAdmin || target.id === user.id) return;
    if (!window.confirm(`¿Eliminar el usuario ${target.username} del CTF y de Guacamole?`)) return;
    if (target.demo) {
      setUsers((current) => current.filter((item) => item.id !== target.id));
      setMessage("Usuario de demostración eliminado de la vista.");
      return;
    }
    try {
      await api.deleteUser(target.id);
      setUsers((current) => current.filter((item) => item.id !== target.id));
      setMessage("Usuario eliminado del CTF y de Guacamole.");
      void loadGuacamole();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo eliminar el usuario");
    }
  };

  const visibleUsers = useMemo(() => {
    const query =
      userSearch.trim().toLowerCase();

    return users.filter(
      (item) => {
        if (!isAdmin && item.role === "admin") return false;
        const matchesRole =
          userRoleFilter === "Todas" ||
          item.role ===
            userRoleFilter;

        const matchesSearch =
          !query ||
          item.username
            .toLowerCase()
            .includes(query) ||
          item.full_name
            .toLowerCase()
            .includes(query) ||
          item.user_function
            .toLowerCase()
            .includes(query) ||
          item.organization
            .toLowerCase()
            .includes(query);

        return (
          matchesRole &&
          matchesSearch
        );
      }
    );
  }, [
    userRoleFilter,
    userSearch,
    users,
    isAdmin,
  ]);

  /* ---------------- PERSISTENCIA DE LABORATORIOS ---------------- */

  const saveLaboratory = async (laboratory: Laboratory) => {
    if (!isAdmin) return;
    if (laboratoryError) {
      setMessage(laboratoryError);
      return;
    }
    const payload = {
      code: laboratory.code,
      name: laboratory.name,
      description: laboratory.description,
      segment: laboratory.environment,
      status: laboratory.status === "Disponible" ? "ready" : laboratory.status === "Mantenimiento" ? "maintenance" : "planned",
    } as const;
    try {
      const isPersisted = /^\d+$/.test(laboratory.id);
      const saved = isPersisted
        ? await api.updateLaboratory(Number(laboratory.id), payload)
        : await api.createLaboratory(payload);
      const mapped = mapBackendLaboratory(saved);
      setLaboratories((current) => isPersisted ? current.map((lab) => lab.id === laboratory.id ? mapped : lab) : [...current, mapped]);
      setSelectedLabId(mapped.id);
      setLabFormOpen(false);
      setMessage(isPersisted ? "Laboratorio actualizado correctamente." : "Laboratorio creado y guardado en la base de datos.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo persistir el laboratorio.");
    }
  };

  const removeLaboratory = async (laboratory: Laboratory) => {
    if (!isAdmin) return;
    if (laboratoryError || !/^\d+$/.test(laboratory.id)) {
      setMessage("Solo se pueden modificar laboratorios confirmados por el servidor.");
      return;
    }
    if (!window.confirm(`¿Eliminar ${laboratory.name}? Esta acción elimina también sus VMs registradas en la plataforma.`)) return;
    try {
      await api.deleteLaboratory(Number(laboratory.id));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo eliminar el laboratorio.");
      return;
    }
    setLaboratories((current) => current.filter((lab) => lab.id !== laboratory.id));
    setSelectedLabId(null);
    setMessage("Laboratorio eliminado correctamente.");
  };

  const saveVM = async (laboratoryId: string, vm: LabVM) => {
    if (!isAdmin) return;
    if (laboratoryError || !/^\d+$/.test(laboratoryId)) {
      setMessage("Selecciona un laboratorio confirmado por el servidor antes de guardar una VM.");
      return;
    }
    const targetLab = laboratories.find((lab) => lab.id === laboratoryId);
    if (!targetLab) return;
    const payload = {
      laboratory_id: Number(laboratoryId),
      name: vm.name,
      os: vm.operatingSystem,
      ip_address: vm.ip || null,
      vlan: vm.vlan || (vm.networkRole === "Atacantes" ? "VLAN 20" : "VLAN 30"),
      role: vm.networkRole || (vm.vlan === "VLAN 20" ? "Atacantes" : "Víctimas"),
      subnet: vm.subnet || (vm.vlan === "VLAN 20" ? "10.10.20.0/24" : "10.10.30.0/24"),
      network_role: vm.networkRole || (vm.vlan === "VLAN 20" ? "Atacantes" : "Víctimas"),
      profile: vm.profile.toLowerCase(),
      status: vm.status || "planned",
      guacamole_connection_id: vm.guacamoleConnectionId || null,
    } as const;
    try {
      const isPersisted = /^\d+$/.test(vm.id);
      const saved = isPersisted ? await api.updateVM(Number(vm.id), payload) : await api.createVM(payload);
      const mapped = mapBackendVM(saved);
      setLaboratories((current) => current.map((lab) => lab.id === laboratoryId ? { ...lab, vms: lab.vms.some((item) => item.id === vm.id) ? lab.vms.map((item) => item.id === vm.id ? mapped : item) : [...lab.vms, mapped] } : lab));
      setMessage("Máquina virtual guardada correctamente.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo persistir la VM.");
    }
  };

  const removeVM = async (laboratoryId: string, vm: LabVM) => {
    if (!isAdmin) return;
    if (laboratoryError || !/^\d+$/.test(vm.id) || !/^\d+$/.test(laboratoryId)) {
      setMessage("Solo se pueden modificar VMs confirmadas por el servidor.");
      return;
    }
    if (!window.confirm(`¿Eliminar la VM ${vm.name}?`)) return;
    try {
      await api.deleteVM(Number(vm.id));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo eliminar la VM.");
      return;
    }
    setLaboratories((current) => current.map((lab) => lab.id === laboratoryId ? { ...lab, vms: lab.vms.filter((item) => item.id !== vm.id) } : lab));
    setMessage("VM eliminada correctamente.");
  };

  // Contrato público del controlador para las vistas MVC.
  return {
    user,
    panelRole,
    view, setView, menuOpen, setMenuOpen,
    challenges, catalogActionBusy, users, setUsers, userSearch, setUserSearch,
    userRoleFilter, setUserRoleFilter,
    userFormOpen, setUserFormOpen, userEditing, setUserEditing,
    ranking, groups, progressRows, setProgressRows, message, setMessage,
    editing, setEditing, creating, setCreating,
    laboratories, setLaboratories, laboratoryError, selectedLabId, setSelectedLabId,
    selectedLab, labFormOpen, setLabFormOpen, labEditing, setLabEditing,
    vmFormOpen, setVmFormOpen, vmEditing, setVmEditing,
    guacamoleConnections, guacamoleMode,
    guacamoleServiceAccount, setGuacamoleServiceAccount,
    guacamoleServicePassword, setGuacamoleServicePassword,
    guacamoleTested, guacamoleStatus, guacamoleUsers, guacamoleLoading,
    guacamoleFormOpen, setGuacamoleFormOpen,
    guacamoleUserEditing, setGuacamoleUserEditing,
    guacamoleConnectionEditing, setGuacamoleConnectionEditing,
    guacamoleConnectionFormOpen, setGuacamoleConnectionFormOpen,
    guacamolePermissionsUser, setGuacamolePermissionsUser, guacamolePermissions,
    guacamolePermissionsOpen, setGuacamolePermissionsOpen,
    isAdmin, published, draft, points, activeUsers, roleLabel, visibleUsers,
    load, loadGuacamole, loadStudentConnection, saveStudentConnection,
    saveGuacamoleUser, deleteGuacamoleManagedUser,
    saveGuacamoleConnection, deleteGuacamoleManagedConnection,
    openGuacamolePermissions, saveGuacamolePermissions,
    saveChallenge, archive, archiveLegacyChallenges, createBeginnerChallengeDrafts,
    changeUser, saveManagedUser, deleteManagedUser,
    saveLaboratory, removeLaboratory, saveVM, removeVM,
  };
}

/** Contrato público consumido por las vistas MVC de gestión. */
export type ManagementController = ReturnType<typeof useManagementController>;
