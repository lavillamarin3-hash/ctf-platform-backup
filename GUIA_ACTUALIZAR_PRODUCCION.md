# Actualizar Cociber CTF desde GitHub, paso a paso

**Para:** la plataforma que ya funciona en Ubuntu Server 26.04, VM web
`10.10.10.13`, con PostgreSQL y Redis nativos en `LAB-DB-POSTGRES:10.10.10.14`.
**Repositorio:** [lavillamarin3-hash/ctf-platform](https://github.com/lavillamarin3-hash/ctf-platform).

La carpeta utilizada como ejemplo es `/opt/ctf-platform`. Si tu instalación está
en otra carpeta, utiliza esa misma en todos los pasos.

## 1. Entender qué sucede al actualizar

GitHub guarda el código del proyecto. Subir un cambio a GitHub no modifica por
sí solo el servidor: debes descargarlo, construir las imágenes y reemplazar
los contenedores que sirven la página.

```text
Editar y probar -> guardar el cambio en GitHub, rama main
                -> descargarlo en Ubuntu con git pull
                -> construir api y web con Docker
                -> recrear api y web -> comprobar en el navegador
```

| Palabra | Significado sencillo |
| --- | --- |
| Repositorio | Carpeta del código y su historial. |
| Rama `main` | Versión del código elegida para desplegar. |
| Commit | Cambio guardado, identificado por un código largo. |
| `pull` | Descargar e incorporar cambios de GitHub. |
| Imagen Docker | Paquete construido con el código y sus dependencias. |
| Contenedor | Ejecución de una imagen. |
| `.env` | Archivo privado del servidor con claves y conexiones. |

Los datos de PostgreSQL y Redis permanecen en la otra VM. Guacamole y su base
de datos conservan su instalación independiente. Esta guía no ejecuta
migraciones de esquema ni cambia sus contraseñas.

Si todavía utilizas las bases antiguas dentro de Docker, prepara primero la
migración siguiendo [README-SETUP](./README-SETUP.md). El procedimiento de vuelta
atrás de esta guía supone que la versión anterior ya utilizaba las BD externas.

## 2. Publicar el cambio en GitHub desde el equipo de trabajo

Si otra persona ya publicó el cambio en `main`, omite este apartado y continúa
con el paso 3. No edites directamente producción para hacer cambios habituales.

En la carpeta del proyecto de tu equipo de trabajo, abre una terminal y revisa:

```bash
git status --short
git branch --show-current
git remote get-url origin
```

Si aparecen archivos modificados, conserva ese trabajo y acuerda cómo guardarlo
antes de cambiar de rama. No uses comandos para borrarlo. Con la copia limpia:

```bash
git switch main
git pull --ff-only origin main
git switch -c mejora/mi-cambio
```

`mejora/mi-cambio` es un nombre de ejemplo para una rama nueva. Edita los archivos
necesarios y ejecuta las pruebas apropiadas al cambio. Revisa qué vas a publicar:

```bash
git diff
git status --short
```

Añade únicamente los archivos del cambio. Por ejemplo, **solo si modificaste
README.md**, los comandos serían:

```bash
git add README.md
git commit -m "Aclara las instrucciones de instalación"
git push -u origin mejora/mi-cambio
```

Para otros cambios, sustituye `README.md` por las rutas reales y utiliza un
mensaje que explique lo realizado. Evita `git add .` si no conoces todos los
archivos pendientes. Nunca añadas `.env`, claves privadas ni copias de bases.

En GitHub, abre el repositorio, crea la solicitud de revisión (**Pull request**)
de esa rama hacia `main` y solicita su revisión. Cuando esté aprobada e
incorporada mediante **Merge**, el cambio estará listo para descargar en el
servidor. Un cambio que siga únicamente en la rama de trabajo todavía no se
despliega con los comandos de esta guía.

## 3. Preparar la actualización de producción

Reserva un momento sin prácticas activas: recrear la API interrumpe conexiones
en vivo y terminales. Informa a los usuarios mediante el canal habitual del
laboratorio y pide que terminen sus sesiones.

Confirma con el responsable una copia de seguridad reciente y recuperable de
PostgreSQL CTF. Guardar imágenes Docker o `.env` no respalda los datos. Si la
versión cambia tablas, detente hasta contar con su procedimiento específico de
migración, copia y recuperación; una actualización de código no lo reemplaza.

En PowerShell de Windows, entra a la VM web:

```powershell
ssh USUARIO_UBUNTU@10.10.10.13
```

Sustituye `USUARIO_UBUNTU`. Introduce la contraseña aunque no se vea al escribir.
Los comandos restantes se ejecutan **en Ubuntu**, uno a uno. Si aparece un
error, detente en ese punto.

```bash
cd /opt/ctf-platform
hostname
git remote get-url origin
git branch --show-current
git status --short
df -h /
sudo docker compose ps
```

Comprueba lo siguiente:

- Estás en el servidor web correcto, no en `LAB-DB-POSTGRES`.
- El remoto es `https://github.com/lavillamarin3-hash/ctf-platform.git` o su
  equivalente SSH, y la rama es `main`.
- `git status --short` no muestra nada: los archivos del repositorio están
  limpios. `.env` se conserva aparte y está excluido de Git.
- Hay espacio disponible y `api` y `web` están en funcionamiento.

Si hay archivos modificados o una rama distinta, pide revisar esa situación
antes de continuar. No uses `reset --hard`, `clean -fd` ni una descarga encima
del proyecto para forzar que quede limpio.

Si utilizas `docker-compose.override.yml`, conserva sus montajes y ajustes.
Comprueba con el responsable que no introduce servicios de BD locales. Los
comandos normales de esta guía conservan la carga automática del override.

## 4. Guardar un punto de recuperación

Haz este paso **antes** de descargar cambios, mientras la versión actual
funciona. La carpeta `work/` está excluida de Git en este repositorio.

```bash
umask 077
mkdir -p work/deploy
chmod 700 work/deploy
git rev-parse HEAD > work/deploy/previous-commit.txt
cp .env "work/deploy/env-$(date +%Y%m%d-%H%M%S).backup"
```

La primera copia guarda el identificador del código anterior. La segunda guarda
las conexiones y secretos: debe permanecer privada en el servidor.

Con los contenedores actuales todavía funcionando, conserva también sus imágenes:

```bash
sudo docker image tag "$(sudo docker compose images -q api)" cociber-api:rollback
sudo docker image tag "$(sudo docker compose images -q web)" cociber-web:rollback
```

Si alguno falla, no continúes hasta guardar ambas imágenes. Estas etiquetas
conservan un solo punto de recuperación y se reemplazan la próxima vez que
ejecutes el paso. No las borres durante la actualización.

## 5. Descargar lo que está en GitHub

```bash
git pull --ff-only origin main
git log -1 --oneline
```

El primer comando descarga los cambios sin crear una mezcla automática de
historiales. Puede mostrar archivos actualizados o `Already up to date` cuando
ya tienes la última versión. Si muestra conflictos, acceso denegado o ramas
divergentes, detente y conserva los archivos para revisión.

El segundo muestra el identificador y el mensaje de la nueva versión. Comprueba
que corresponde al cambio que deseas publicar.

Lee las instrucciones de esa versión. Si `.env.example` tiene nuevas variables,
añade únicamente las necesarias a tu `.env` usando `nano .env`. **No ejecutes
`cp .env.example .env` durante una actualización.** Conserva `JWT_SECRET`,
`FIELD_HMAC_SECRET`, las credenciales de BD, `GUACAMOLE_*`, el inyector SSH y sus
archivos montados.

La dirección `PUBLIC_ORIGIN` debe coincidir con la que abre el usuario, incluido
el puerto si lo utiliza, sin barra final. El ejemplo es `http://10.10.10.13`.
Si tu instalación usa HTTPS, conserva su origen HTTPS y su proxy.

## 6. Construir la nueva versión

```bash
sudo docker compose config --quiet
sudo docker compose config --services
sudo docker compose build api web
```

Ejecuta cada línea por separado. La primera no imprime nada cuando es válida.
La segunda debe listar solamente `api` y `web`. La tercera instala dependencias
en las imágenes y compila la interfaz. Espera hasta que termine sin errores.

Durante la construcción continúan funcionando los contenedores anteriores.
Si falla por espacio, conexión o compilación, corrige el problema antes de
reemplazarlos. No limpies volúmenes ni borres las imágenes `:rollback`.

No basta con `docker compose restart`: reiniciar reutiliza el código de la
imagen anterior. Tampoco basta con actualizar solamente el navegador.

## 7. Comprobar las BD antes de reemplazar la web

```bash
sudo docker compose run --rm --no-deps api python -m app.check_services
```

Debes obtener:

```text
PostgreSQL (lectura de users): OK
Redis (PING): OK
```

Se crea un contenedor temporal de la imagen nueva, se comprueban las conexiones
y se elimina al terminar. No se crean tablas ni datos. `ERROR` significa que
debes revisar conexión, credenciales, TLS, esquema o permisos antes de continuar.
El control no certifica todos los permisos SQL/Redis ni todas las tablas.

## 8. Aplicar la nueva versión

```bash
sudo docker compose up -d --force-recreate --wait --wait-timeout 180 api web
sudo docker compose ps
```

Este paso reemplaza ambos contenedores y produce una interrupción breve. Nginx
también se recrea para resolver correctamente la dirección de la API. El comando
espera hasta tres minutos a que los controles indiquen `healthy`.

Si falla o termina por tiempo agotado, la actualización no está confirmada.
Consulta los registros y sigue el apartado de problemas o recuperación. No
supongas que Docker vuelve automáticamente a las imágenes anteriores.

## 9. Comprobar como usuario

```bash
sudo docker compose exec -T api python -m app.check_services --http
curl --fail http://10.10.10.13/api/v1/health
```

Si utilizas otro puerto o un proxy HTTPS, sustituye la dirección de `curl` por
la real. Los tres controles deben indicar `OK`; la respuesta de la API debe
incluir `"status":"ok"`. El endpoint HTTP por sí solo no comprueba las BD.

Abre la web y realiza esta revisión:

1. Pulsa **Ctrl+F5** para recargar los archivos de la interfaz.
2. Inicia sesión con una cuenta que ya existía.
3. Revisa que se conservan los datos, retos y puntuaciones esperados.
4. Abre la pantalla modificada y comprueba el cambio concreto publicado.
5. Comprueba el ranking y una práctica autorizada. Si utilizas Guacamole o SSH,
   abre y cierra una sesión para verificar también esa integración.

Si todo funciona, registra la versión desplegada:

```bash
git rev-parse HEAD > work/deploy/deployed-commit.txt
```

Conserva el punto de recuperación hasta confirmar estabilidad. La opción de
reinicio automático mantiene los contenedores si el proceso termina, pero el
estado `unhealthy` por sí solo no provoca un reinicio ni corrige un error.

## 10. Si aparece un problema

```bash
sudo docker compose ps
sudo docker compose logs --tail=80 api web
```

No publiques los registros completos sin revisar si contienen información privada.

| Problema | Acción |
| --- | --- |
| Git no descarga | Revisar red, URL y acceso a GitHub. No poner tokens en la URL. |
| Falla `build` | Leer el error de dependencias o compilación; los contenedores anteriores siguen funcionando si no ejecutaste el paso 8. |
| Falla PostgreSQL o Redis | Revisar con el responsable los servicios de `10.10.10.14`, credenciales, TLS y permisos. No cambiar a una base vacía. |
| El puerto está ocupado | Revisar el proxy y el puerto existente; no detener otro servicio sin identificarlo. |
| Error 502 | Revisar salud de API y recreación de ambos servicios; comprobar los registros de Nginx. |
| La página sigue igual | Confirmar commit descargado, construcción exitosa, recreación de `web` y Ctrl+F5. |
| Hay errores de columnas o tablas | Detener el despliegue y revisar la migración de esa versión. No activar datos de demostración. |
| Guacamole o una terminal falla | Comparar configuración privada, origen del navegador, proxy WebSocket y montajes SSH existentes. |

No ejecutes `docker compose down -v`, `docker volume prune` ni limpiezas globales
para corregir una actualización. No es necesario parar las BD ni Guacamole.

## 11. Volver a la versión anterior si es necesario

Este procedimiento requiere las dos imágenes `:rollback` y el archivo
`previous-commit.txt` guardados en el paso 4. Úsalo solo si la versión anterior
ya funcionaba con las BD externas y **su esquema continúa siendo compatible**.
Si hubo una migración de datos o tablas, el responsable debe decidir cómo
recuperar el servicio antes de ejecutar estos comandos.

Primero verifica que no hay cambios locales pendientes:

```bash
git status --short
```

Si muestra archivos, detente para conservarlos. Con la copia limpia:

```bash
git switch --detach "$(cat work/deploy/previous-commit.txt)"
```

Ahora estás viendo el código anterior. El mensaje `detached HEAD` es esperado:
estás en una versión concreta del historial, fuera de una rama.

Crea un pequeño archivo que seleccione las imágenes conservadas. Copia el bloque
completo, incluida la última línea `YAML`, en la terminal de Ubuntu:

```bash
cat > work/deploy/rollback-images.yml <<'YAML'
services:
  api:
    image: cociber-api:rollback
  web:
    image: cociber-web:rollback
YAML
```

Si tu instalación utiliza únicamente `docker-compose.yml`, ejecuta:

```bash
sudo docker compose -f docker-compose.yml -f work/deploy/rollback-images.yml up -d --no-build --pull never --force-recreate --wait --wait-timeout 180 api web
sudo docker compose -f docker-compose.yml -f work/deploy/rollback-images.yml ps
```

**Si existe `docker-compose.override.yml` con ajustes necesarios**, debes
conservarlo también. En ese caso, utiliza estas dos líneas en lugar de las anteriores:

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.override.yml -f work/deploy/rollback-images.yml up -d --no-build --pull never --force-recreate --wait --wait-timeout 180 api web
sudo docker compose -f docker-compose.yml -f docker-compose.override.yml -f work/deploy/rollback-images.yml ps
```

`--no-build --pull never` utiliza las imágenes guardadas en el servidor. Comprueba
de nuevo el inicio de sesión, los datos y las funciones del paso 9. Esta operación
no restaura una base ni sobrescribe `.env`; si cambiaste una variable, compara
privadamente la copia guardada y recupera solo lo necesario con el responsable.

Para intentar desplegar una versión corregida más adelante, vuelve a la rama:

```bash
git switch main
```

Después del retorno, **conserva el punto de recuperación anterior y no repitas
el paso 4** mientras la versión que está funcionando sea la recuperada: `main`
podría señalar todavía el código que falló. Cuando el arreglo esté incorporado,
retoma desde el paso 5 y realiza las comprobaciones hasta el paso 9. Tras un
despliegue confirmado, el siguiente mantenimiento podrá crear un nuevo punto.

## 12. Lista breve para futuras actualizaciones

1. Confirmar el cambio en GitHub `main`, ventana de mantenimiento y copia de BD.
2. Entrar a la VM web y comprobar repositorio limpio y servicios actuales.
3. Guardar commit, `.env` privado e imágenes anteriores.
4. Descargar con `git pull --ff-only origin main`.
5. Revisar variables nuevas sin reemplazar `.env`.
6. Validar configuración, construir `api` y `web` y comprobar las BD.
7. Recrear ambos servicios y esperar estado saludable.
8. Verificar en el navegador el cambio y las funciones existentes.
9. Registrar el commit desplegado y conservar el punto de recuperación.

Referencias: [git pull y avance directo](https://git-scm.com/docs/git-pull),
[docker compose up](https://docs.docker.com/reference/cli/docker/compose/up/) y
[configuración inicial del proyecto](./README-SETUP.md).
