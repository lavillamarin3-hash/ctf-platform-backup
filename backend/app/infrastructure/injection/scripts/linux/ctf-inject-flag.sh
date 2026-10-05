#!/usr/bin/env bash
# ============================================================
# INYECTOR DE FLAGS DEL LABORATORIO CTF
# Ejecutar solo mediante sudoers y desde la cuenta de servicio.
# ============================================================
set -euo pipefail

FLAG_PATH=""
FLAG_VALUE=""
CLEAR_FLAG="false"
FLAG_ARGUMENT_PRESENT="false"
FLAG_FROM_STDIN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)
      FLAG_PATH="${2:-}"
      shift 2
      ;;
    --flag)
      FLAG_VALUE="${2:-}"
      FLAG_ARGUMENT_PRESENT="true"
      shift 2
      ;;
    --stdin)
      FLAG_FROM_STDIN="true"
      shift
      ;;
    --clear)
      CLEAR_FLAG="true"
      shift
      ;;
    *)
      echo "Argumento no permitido" >&2
      exit 2
      ;;
  esac
done

# La cuenta de servicio nunca debe poder escribir fuera del árbol CTF.
# Rechazar componentes relativos y enlaces simbólicos evita que una ruta que
# comience por /opt/ctf termine resolviéndose fuera de ese árbol.
case "$FLAG_PATH" in
  /opt/ctf/*) ;;
  *) echo "Ruta no permitida" >&2; exit 3 ;;
esac
relative_path="${FLAG_PATH#/opt/ctf/}"
if [[ -z "$relative_path" || "$relative_path" == */ || "$relative_path" == *//* ||
      "$FLAG_PATH" =~ [[:cntrl:]] ]]; then
  echo "Ruta no permitida" >&2
  exit 3
fi
IFS='/' read -r -a path_parts <<< "$relative_path"
for part in "${path_parts[@]}"; do
  if [[ -z "$part" || "$part" == . || "$part" == .. ]]; then
    echo "Ruta no permitida" >&2
    exit 3
  fi
done

private_evidence="false"
if [[ "$FLAG_PATH" == /opt/ctf/ESC-01-RECON/flag.txt ]]; then
  private_evidence="true"
fi
if [[ "$private_evidence" == "true" ]]; then
  if [[ "$FLAG_ARGUMENT_PRESENT" == "true" || ( "$CLEAR_FLAG" != "true" && "$FLAG_FROM_STDIN" != "true" ) ]]; then
    echo "La evidencia de ESC requiere stdin y no admite --flag" >&2
    exit 4
  fi
elif [[ "$FLAG_FROM_STDIN" == "true" ]]; then
  echo "stdin solo está permitido para la evidencia de ESC" >&2
  exit 4
fi
if [[ "$CLEAR_FLAG" == "true" && "$FLAG_FROM_STDIN" == "true" ]]; then
  echo "No se admite stdin al limpiar evidencia" >&2
  exit 4
fi

flag_directory="$(dirname -- "$FLAG_PATH")"
current_directory=""
IFS='/' read -r -a directory_parts <<< "${flag_directory#/}"
for part in "${directory_parts[@]}"; do
  current_directory="${current_directory}/${part}"
  if [[ -L "$current_directory" ]]; then
    echo "Ruta no permitida: directorio simbólico" >&2
    exit 3
  fi
  if [[ -e "$current_directory" ]]; then
    if [[ ! -d "$current_directory" || "$(stat -c %u -- "$current_directory")" != 0 ]]; then
      echo "Ruta no permitida: directorio no controlado por root" >&2
      exit 3
    fi
    directory_mode="$(stat -c %a -- "$current_directory")"
    if (( (8#$directory_mode & 0022) != 0 )); then
      echo "Ruta no permitida: directorio modificable por otros" >&2
      exit 3
    fi
  fi
done
if [[ -L "$FLAG_PATH" || -d "$FLAG_PATH" ]]; then
  echo "Ruta no permitida: destino no es un archivo regular" >&2
  exit 3
fi

if [[ "$CLEAR_FLAG" == "true" ]]; then
  rm -f -- "$FLAG_PATH"
  [[ ! -e "$FLAG_PATH" ]] || { echo "No se pudo limpiar la bandera" >&2; exit 7; }
  printf '%s\n' "CLEARED"
  exit 0
fi

if [[ "$FLAG_FROM_STDIN" == "true" ]]; then
  # El backend transmite una sola línea y cierra el canal de escritura.
  # Nunca incluir su valor en argumentos, mensajes o registros.
  if ! IFS= read -r FLAG_VALUE; then
    echo "No se recibió una línea de evidencia" >&2
    exit 4
  fi
  extra_line=""
  if IFS= read -r extra_line || [[ -n "$extra_line" ]]; then
    echo "La evidencia debe ocupar una sola línea" >&2
    exit 4
  fi
  if (( ${#FLAG_VALUE} > 511 )) || [[ "$FLAG_VALUE" =~ [[:cntrl:]] ]]; then
    echo "Formato de evidencia no permitido" >&2
    exit 4
  fi
fi
if [[ -z "$FLAG_VALUE" ]]; then
  echo "La bandera no puede estar vacía" >&2
  exit 4
fi

if [[ ! -d /opt/ctf ]]; then
  install -d -o root -g root -m 0755 /opt/ctf
fi
if [[ "$private_evidence" == "true" ]]; then
  # ESC no debe revelar la evidencia a una sesión interactiva en la víctima.
  # LAB-01 mantiene sus permisos heredados para no romper su reto SSH.
  if ! getent group ctf-evidence >/dev/null; then
    echo "Falta el grupo del servicio de evidencia" >&2
    exit 8
  fi
  if [[ ! -d "$flag_directory" ]]; then
    install -d -o root -g ctf-evidence -m 0750 "$flag_directory"
  else
    chown root:ctf-evidence "$flag_directory"
    chmod 0750 "$flag_directory"
  fi
else
  if [[ ! -d "$flag_directory" ]]; then
    install -d -o root -g root -m 0755 "$flag_directory"
  fi
fi
tmp_file="$(mktemp "$flag_directory/.flag.XXXXXX")"
trap 'rm -f -- "$tmp_file"' EXIT
printf '%s\n' "$FLAG_VALUE" > "$tmp_file"
if [[ "$private_evidence" == "true" ]]; then
  chown root:ctf-evidence "$tmp_file"
  chmod 0640 "$tmp_file"
else
  chmod 0644 "$tmp_file"
fi
mv -f "$tmp_file" "$FLAG_PATH"

# Verificación mínima: confirmar que el archivo existe y contiene una sola línea.
[[ -s "$FLAG_PATH" ]] || { echo "No se pudo confirmar la escritura" >&2; exit 5; }
[[ "$(wc -l < "$FLAG_PATH")" -ge 1 ]] || { echo "Contenido inválido" >&2; exit 6; }

printf '%s\n' "OK"
