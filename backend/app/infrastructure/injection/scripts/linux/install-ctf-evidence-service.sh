#!/usr/bin/env bash
# Instalación manual y sin Internet del servicio de evidencia de ESC-01-RECON.
# No crea, lee, reemplaza ni elimina ningún archivo de flag.
set -euo pipefail
umask 077

SERVICE_USER="ctf-evidence"
SERVICE_NAME="ctf-evidence.service"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="$SOURCE_DIR/ctf-evidence-service.py"
SOURCE_INJECTOR="$SOURCE_DIR/ctf-inject-flag.sh"
TARGET_SCRIPT="/usr/local/lib/ctf/ctf-evidence-service.py"
TARGET_INJECTOR="/usr/local/sbin/ctf-inject-flag.sh"
UNIT_FILE="/etc/systemd/system/$SERVICE_NAME"
EVIDENCE_DIR="/opt/ctf/ESC-01-RECON"
EVIDENCE_FLAG="$EVIDENCE_DIR/flag.txt"

fail() {
  printf 'Instalación detenida: %s\n' "$1" >&2
  exit 1
}

[[ "$(id -u)" == 0 ]] || fail "ejecuta este instalador con sudo en la VM 192.168.146.137"
[[ -x /usr/bin/python3 ]] || fail "Python 3 no está disponible en /usr/bin/python3"
[[ -x /usr/sbin/nologin ]] || fail "falta /usr/sbin/nologin"
command -v systemctl >/dev/null || fail "systemd no está disponible"
[[ -f "$SOURCE_SCRIPT" && ! -L "$SOURCE_SCRIPT" ]] || fail "falta ctf-evidence-service.py junto al instalador"
[[ -f "$SOURCE_INJECTOR" && ! -L "$SOURCE_INJECTOR" ]] || fail "falta ctf-inject-flag.sh junto al instalador"

# El inyector previamente instalado debe ser la versión endurecida. No se
# sobrescribe automáticamente: antes hay que cerrar corridas y actualizarlo
# de manera explícita, conservando una copia del archivo anterior.
[[ -f "$TARGET_INJECTOR" && ! -L "$TARGET_INJECTOR" ]] || fail "no existe el inyector instalado en $TARGET_INJECTOR"
cmp -s -- "$SOURCE_INJECTOR" "$TARGET_INJECTOR" || fail "el inyector instalado es distinto; actualízalo por separado antes de instalar este servicio"
[[ "$(stat -c %u -- "$TARGET_INJECTOR")" == 0 ]] || fail "el inyector instalado no pertenece a root"
injector_mode="$(stat -c %a -- "$TARGET_INJECTOR")"
if (( (8#$injector_mode & 0022) != 0 )); then
  fail "el inyector instalado permite escrituras de otros usuarios"
fi

for safe_dir in /opt /opt/ctf "$EVIDENCE_DIR" /usr/local/lib/ctf; do
  [[ ! -L "$safe_dir" ]] || fail "$safe_dir es un enlace simbólico"
  [[ ! -e "$safe_dir" || -d "$safe_dir" ]] || fail "$safe_dir no es un directorio"
  if [[ -d "$safe_dir" ]]; then
    [[ "$(stat -c %u -- "$safe_dir")" == 0 ]] || fail "$safe_dir no pertenece a root"
    directory_mode="$(stat -c %a -- "$safe_dir")"
    if (( (8#$directory_mode & 0022) != 0 )); then
      fail "$safe_dir permite escrituras de otros usuarios"
    fi
  fi
done
[[ ! -e "$EVIDENCE_FLAG" && ! -L "$EVIDENCE_FLAG" ]] || fail "hay una flag de ESC-01-RECON; cierra la corrida antes de instalar"

TEMP_UNIT="$(mktemp)"
trap 'rm -f -- "$TEMP_UNIT"' EXIT
cat > "$TEMP_UNIT" <<'UNIT'
[Unit]
Description=CTF ESC-01-RECON evidence service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=ctf-evidence
Group=ctf-evidence
ExecStart=/usr/bin/python3 -B /usr/local/lib/ctf/ctf-evidence-service.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_UNIX
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT

for pair in "$SOURCE_SCRIPT:$TARGET_SCRIPT" "$TEMP_UNIT:$UNIT_FILE"; do
  source_file="${pair%%:*}"
  target_file="${pair#*:}"
  if [[ -e "$target_file" || -L "$target_file" ]]; then
    [[ -f "$target_file" && ! -L "$target_file" ]] || fail "$target_file no es un archivo regular"
    cmp -s -- "$source_file" "$target_file" || fail "$target_file ya existe con contenido distinto; revísalo manualmente"
    [[ "$(stat -c %u -- "$target_file")" == 0 ]] || fail "$target_file no pertenece a root"
    file_mode="$(stat -c %a -- "$target_file")"
    if (( (8#$file_mode & 0022) != 0 )); then
      fail "$target_file permite escrituras de otros usuarios"
    fi
  fi
done

if id -u "$SERVICE_USER" >/dev/null 2>&1; then
  [[ "$(id -gn "$SERVICE_USER")" == "$SERVICE_USER" ]] || fail "la cuenta $SERVICE_USER tiene un grupo principal inesperado"
  [[ "$(id -nG "$SERVICE_USER")" == "$SERVICE_USER" ]] || fail "la cuenta $SERVICE_USER pertenece a grupos adicionales"
  account_shell="$(getent passwd "$SERVICE_USER" | cut -d: -f7)"
  case "$account_shell" in
    /usr/sbin/nologin|/sbin/nologin|/bin/false) ;;
    *) fail "la cuenta $SERVICE_USER permite inicio de sesión; revísala manualmente" ;;
  esac
else
  ! getent group "$SERVICE_USER" >/dev/null || fail "el grupo $SERVICE_USER existe sin la cuenta correspondiente"
  useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$SERVICE_USER"
fi
service_gid="$(id -g "$SERVICE_USER")"
other_primary_users="$(getent passwd | awk -F: -v gid="$service_gid" -v user="$SERVICE_USER" '$4 == gid && $1 != user { print $1 }')"
[[ -z "$other_primary_users" ]] || fail "hay otras cuentas con el grupo principal $SERVICE_USER"
supplementary_members="$(getent group "$SERVICE_USER" | cut -d: -f4)"
[[ -z "$supplementary_members" ]] || fail "el grupo $SERVICE_USER tiene miembros adicionales"

if [[ ! -d /opt/ctf ]]; then
  install -d -o root -g root -m 0755 /opt/ctf
fi
if [[ ! -d "$EVIDENCE_DIR" ]]; then
  install -d -o root -g "$SERVICE_USER" -m 0750 "$EVIDENCE_DIR"
else
  [[ "$(stat -c %u:%g -- "$EVIDENCE_DIR")" == "0:$(id -g "$SERVICE_USER")" ]] || fail "$EVIDENCE_DIR tiene propietario/grupo distintos; revísalos manualmente"
  [[ "$(stat -c %a -- "$EVIDENCE_DIR")" == 750 ]] || fail "$EVIDENCE_DIR debe tener modo 0750; revísalo manualmente"
fi

if [[ ! -f "$TARGET_SCRIPT" ]]; then
  install -d -o root -g root -m 0755 /usr/local/lib/ctf
  install -o root -g root -m 0644 "$SOURCE_SCRIPT" "$TARGET_SCRIPT"
fi
if [[ ! -f "$UNIT_FILE" ]]; then
  install -o root -g root -m 0644 "$TEMP_UNIT" "$UNIT_FILE"
fi

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
healthy="false"
for _attempt in 1 2 3 4 5; do
  # HEAD no transmite el contenido de la flag. Desde la propia víctima la
  # respuesta esperada es 403, ya que únicamente .134 puede consultar el reto.
  status="$(/usr/bin/python3 -c 'from urllib.request import Request, urlopen; from urllib.error import HTTPError; req = Request("http://192.168.146.137:18081/evidence", method="HEAD");
try:
    response = urlopen(req, timeout=1)
    print(response.status)
except HTTPError as error:
    print(error.code)' 2>/dev/null || true)"
  if [[ "$status" == 403 ]] && systemctl is-active --quiet "$SERVICE_NAME"; then
    healthy="true"
    break
  fi
  sleep 1
done
[[ "$healthy" == "true" ]] || fail "el servicio no respondió 403 al HEAD local; verifica que la VM conserve la IP 192.168.146.137"
printf 'Servicio instalado y activo. Desde Kali 192.168.146.134, comprueba HEAD /evidence: 404 sin corrida.\n'
