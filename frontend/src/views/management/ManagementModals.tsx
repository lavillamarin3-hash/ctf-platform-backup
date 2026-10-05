// ============================================================
// MODALES DE GESTIÓN
// Responsabilidad: altas y ediciones desde el panel administrativo.
// ============================================================

import { createElement } from "react";
import type { ManagementController } from "../../controllers/useManagementController";
import { ChallengeForm } from "../../components/challenges";
import { UserForm } from "../../components/users";
import { GuacamoleUserForm, GuacamoleConnectionForm, GuacamolePermissionsForm } from "../../components/guacamole";
import { LaboratoryForm, VMForm } from "../../components/laboratory";

export function ManagementModals({ controller }: { controller: ManagementController }) {
  const c = controller;
  return <>
    {c.creating && <ChallengeForm initial={c.editing} laboratories={c.laboratories} groups={c.groups} categories={c.challenges.map((challenge) => challenge.category)} onClose={() => { c.setCreating(false); c.setEditing(null); }} onSave={c.saveChallenge} />}
    {c.userFormOpen && c.isAdmin && <UserForm initial={c.userEditing} onClose={() => { c.setUserFormOpen(false); c.setUserEditing(null); }} onSave={c.saveManagedUser} />}
    {c.labFormOpen && <LaboratoryForm initial={c.labEditing} onClose={() => { c.setLabFormOpen(false); c.setLabEditing(null); }} onSave={c.saveLaboratory} />}
    {c.vmFormOpen && c.selectedLab && <VMForm laboratory={c.selectedLab} initial={c.vmEditing} onClose={() => { c.setVmFormOpen(false); c.setVmEditing(null); }} onSave={c.saveVM} guacamoleConnections={c.guacamoleConnections} />}
    {c.guacamoleFormOpen && c.isAdmin && <GuacamoleUserForm initial={c.guacamoleUserEditing} onClose={() => { c.setGuacamoleFormOpen(false); c.setGuacamoleUserEditing(null); }} onSave={c.saveGuacamoleUser} />}
    {c.guacamoleConnectionFormOpen && c.isAdmin && <GuacamoleConnectionForm initial={c.guacamoleConnectionEditing} onClose={() => { c.setGuacamoleConnectionFormOpen(false); c.setGuacamoleConnectionEditing(null); }} onSave={c.saveGuacamoleConnection} />}
    {c.guacamolePermissionsOpen && c.guacamolePermissionsUser && c.isAdmin && <GuacamolePermissionsForm username={c.guacamolePermissionsUser} initial={c.guacamolePermissions} connections={c.guacamoleConnections} onClose={() => { c.setGuacamolePermissionsOpen(false); c.setGuacamolePermissionsUser(null); }} onSave={c.saveGuacamolePermissions} />}
  </>;
}
