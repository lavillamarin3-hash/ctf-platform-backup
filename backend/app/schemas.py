# ============================================================
# CONTRATOS DE LA API
# Responsabilidad: validar y tipar los payloads de entrada y salida mediante Pydantic.
# ============================================================

from __future__ import annotations

from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str | None
    role: str
    is_active: bool
    full_name: str | None = None
    organization: str | None = None
    user_function: str | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    email: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=256)
    role: str = Field(pattern=r"^(admin|instructor|player|guest)$")
    full_name: str | None = Field(default=None, max_length=160)
    organization: str | None = Field(default=None, max_length=160)
    user_function: str | None = Field(default=None, max_length=80)
    sync_guacamole: bool = True


class GuacamoleUserView(BaseModel):
    username: str
    attributes: dict = Field(default_factory=dict)
    last_active: int | None = None


class GuacamoleUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=256)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=160)


class GuacamoleUserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=256)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=160)
    disabled: bool | None = None


class GuacamoleConnectionView(BaseModel):
    identifier: str
    name: str
    protocol: str
    parent_identifier: str = "ROOT"
    hostname: str | None = None
    port: str | None = None
    parameters: dict = Field(default_factory=dict)
    attributes: dict = Field(default_factory=dict)
    active_connections: int = 0


class GuacamoleConnectionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    protocol: str = Field(pattern=r"^(ssh|rdp|vnc)$")
    hostname: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=512)
    domain: str | None = Field(default=None, max_length=255)
    parent_identifier: str = Field(default="ROOT", max_length=64)


class GuacamoleConnectionUpdate(GuacamoleConnectionCreate):
    password: str | None = Field(default=None, max_length=512)


class GuacamolePermissionSet(BaseModel):
    system_permissions: list[str] = Field(default_factory=list)
    connection_permissions: dict[str, list[str]] = Field(default_factory=dict)


class GuacamolePermissionPatch(BaseModel):
    system_permissions: list[str] = Field(default_factory=list)
    connection_permissions: dict[str, list[str]] = Field(default_factory=dict)


class GuacamoleStatus(BaseModel):
    mode: str
    connected: bool
    base_url: str
    data_source: str
    username: str
    user_count: int | None = None


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(admin|instructor|player|guest)$")
    is_active: bool | None = None
    full_name: str | None = Field(default=None, max_length=160)
    organization: str | None = Field(default=None, max_length=160)
    user_function: str | None = Field(default=None, max_length=80)


class ProfileUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str | None = Field(default=None, max_length=255)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class FlagView(BaseModel):
    id: int
    label: str
    flag_order: int
    is_active: bool
    mode: str = "static"
    template: str | None = None


class ChallengeView(BaseModel):
    id: int
    code: str
    name: str
    description: str
    instructions: str = ""
    difficulty: str
    category: str
    scenario: str | None = None
    mitre_technique: str
    asset_references: list[str]
    points: int
    is_published: bool
    flag_count: int = 0
    completed: bool = False
    flags: list[FlagView] | None = None


class ChallengeCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9-]{3,64}$")
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=8000)
    instructions: str = Field(default="", max_length=8000)
    difficulty: str = Field(pattern=r"^(Básico|Medio|Avanzado)$")
    category: str = Field(min_length=2, max_length=48)
    scenario: str | None = Field(default=None, max_length=64)
    mitre_technique: str = Field(min_length=3, max_length=64)
    asset_references: list[str] = Field(min_length=1, max_length=8)
    points: int = Field(ge=1, le=10000)
    is_published: bool = True

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        # La categoría se guarda en challenges.category (VARCHAR(48)); no se
        # requiere una tabla nueva. Conservamos el formato histórico en mayúsculas.
        if re.search(r"[\r\n\t]", value):
            raise ValueError("La categoría no puede contener saltos de línea ni tabulaciones.")
        normalized = " ".join(value.strip().split()).upper()
        if not re.fullmatch(r"[A-ZÁÉÍÓÚÜÑ0-9][A-ZÁÉÍÓÚÜÑ0-9 /_-]{1,47}", normalized):
            raise ValueError("La categoría debe tener de 2 a 48 caracteres: letras, números, espacios, /, _ o -.")
        return normalized


class FlagCreate(BaseModel):
    label: str = Field(min_length=2, max_length=120)
    value: str | None = Field(default=None, min_length=4, max_length=512)
    flag_order: int = Field(ge=1, le=10)
    mode: str = Field(default="static", pattern=r"^(static|dynamic)$")
    template: str | None = Field(default=None, max_length=512)


class FlagUpdate(FlagCreate):
    is_active: bool = True


class SubmissionRequest(BaseModel):
    value: str = Field(min_length=1, max_length=512)


class SubmissionResponse(BaseModel):
    correct: bool
    challenge_completed: bool
    awarded_points: int
    message: str


class RankingRow(BaseModel):
    position: int
    username: str
    total_points: int
    challenges_completed: int


class RankingResponse(BaseModel):
    rows: list[RankingRow]


class RunView(BaseModel):
    id: int
    challenge_code: str
    status: str
    started_at: datetime
    expires_at: datetime
    launch_url: str | None = None
    connection_state: str | None = None
    workspace_strategy: str
    target_vm_name: str | None = None
    target_vm_ip: str | None = None
    target_protocol: str | None = None
    laboratory_code: str | None = None




class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Z0-9_-]+$")
    description: str = Field(default="", max_length=300)
    is_active: bool = True


class GroupMemberAdd(BaseModel):
    user_id: int = Field(ge=1)


class ChallengeGroupAssignmentRequest(BaseModel):
    group_id: int = Field(ge=1)


class GroupMemberView(BaseModel):
    user_id: int
    username: str
    email: str | None = None
    is_active: bool


class GroupChallengeView(BaseModel):
    challenge_id: int
    code: str
    name: str


class GroupView(BaseModel):
    id: int
    name: str
    code: str
    description: str
    is_active: bool
    guacamole_group_identifier: str | None = None
    members: list[GroupMemberView] = Field(default_factory=list)
    challenges: list[GroupChallengeView] = Field(default_factory=list)

    @classmethod
    def from_model(cls, group):
        return cls(
            id=group.id, name=group.name, code=group.code, description=group.description, is_active=group.is_active, guacamole_group_identifier=group.guacamole_group_identifier,
            members=[GroupMemberView(user_id=m.user.id, username=m.user.username, email=m.user.email, is_active=m.user.is_active) for m in group.members],
            challenges=[GroupChallengeView(challenge_id=a.challenge.id, code=a.challenge.code, name=a.challenge.name) for a in group.challenge_assignments],
        )


class VMView(BaseModel):
    id: int
    laboratory_id: int
    name: str
    os: str
    ip_address: str | None
    vlan: str
    role: str
    network_role: str
    subnet: str
    profile: str
    baseline: str | None
    nutanix_vm_id: str | None
    guacamole_connection_id: str | None = None
    guacamole_url: str | None = None
    guacamole_protocol: str | None = None
    status: str


class LaboratoryView(BaseModel):
    id: int
    code: str | None
    name: str
    description: str
    segment: str
    status: str
    vms: list[VMView] = Field(default_factory=list)


class LaboratoryCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=300)
    segment: str = Field(default="VLAN 30 · 10.10.30.0/24", max_length=64)
    status: str = Field(default="planned", pattern=r"^(planned|ready|maintenance|offline)$")


class VMCreate(BaseModel):
    laboratory_id: int
    name: str = Field(min_length=3, max_length=120)
    os: str = Field(default="Por definir", max_length=120)
    ip_address: str | None = Field(default=None, max_length=64)
    vlan: str = Field(default="VLAN 30", max_length=32)
    role: str = Field(default="Víctimas", max_length=120)
    network_role: str = Field(default="Víctimas", max_length=64)
    subnet: str = Field(default="10.10.30.0/24", max_length=64)
    profile: str = Field(default="standard", pattern=r"^(vulnerable|standard|hardened)$")
    baseline: str | None = Field(default=None, max_length=160)
    nutanix_vm_id: str | None = Field(default=None, max_length=160)
    guacamole_connection_id: str | None = Field(default=None, max_length=160)
    status: str = Field(default="ready", pattern=r"^(planned|ready|maintenance|offline)$")


class VMUpdate(VMCreate):
    pass
