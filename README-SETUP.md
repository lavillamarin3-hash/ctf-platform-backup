# Instalar Cociber CTF en producción

Guía para Ubuntu Live Server 26.04. Servidor web: **10.10.10.13/24**.
Servidor de bases de datos: **LAB-DB-POSTGRES, 10.10.10.14**.

Si la plataforma ya funciona y únicamente deseas publicar cambios del código,
ve directamente a [Actualizar desde GitHub](./GUIA_ACTUALIZAR_PRODUCCION.md).

## 1. Qué estamos instalando

La plataforma tiene una parte visible, llamada **frontend**, y una parte que
procesa las acciones, llamada **backend** o **API**. Docker las ejecuta en
contenedores: entornos con las dependencias que necesita cada parte.

| Componente | Dónde funciona | Qué guarda o hace |
| --- | --- | --- |
| Web/Nginx | VM web `10.10.10.13`, contenedor `web` | Presenta las pantallas y dirige las peticiones hacia la API. |
| API FastAPI | VM web, contenedor `api` | Valida usuarios, retos, flags y puntuaciones. |
| PostgreSQL | VM `10.10.10.14`, servicio nativo, puerto `5432` | Guarda los datos permanentes de la plataforma. |
| Redis | VM `10.10.10.14`, servicio nativo, puerto `6379` | Da soporte a eventos, caché y coordinación de la aplicación. |
| Apache Guacamole | Instalación existente | Proporciona acceso remoto y mantiene su propia base de datos. |

```text
Navegador del usuario
        |
        v
10.10.10.13:80 -> web/Nginx -> api:8000 (red interna de Docker)
                                |-> 10.10.10.14:5432 PostgreSQL CTF
                                |-> 10.10.10.14:6379 Redis CTF
                                |-> Guacamole existente, según su configuración
```

El archivo `docker-compose.yml` contiene solamente `api` y `web`. No instala
PostgreSQL, Redis ni Guacamole. Las dependencias de Python y Node se instalan
durante la construcción de las imágenes; no necesitas instalar Python, Node o
Nginx directamente en Ubuntu para este despliegue.

## 2. Información que debes tener antes de empezar

Solicita al responsable del laboratorio estos datos. **No publiques contraseñas
en GitHub ni las incluyas en capturas.**

- Usuario de Ubuntu con permiso para ejecutar `sudo` en `10.10.10.13`.
- Confirmación de que PostgreSQL y Redis están funcionando en `10.10.10.14`.
- Nombre de la base CTF, usuario PostgreSQL y su contraseña.
- Usuario ACL de Redis y su contraseña, que puede ser diferente.
- Una base CTF con datos migrados o un esquema compatible ya preparado, y una
  cuenta administradora de la **plataforma**. Esta cuenta no es la de PostgreSQL.
- Configuración privada de Guacamole y del inyector SSH, si ya se utilizan.
- Una copia de seguridad recuperable de la base CTF antes de migrarla.

El ejemplo utiliza la base `cociber_ctf` y cuentas `cociber_app`. Debes sustituir
estos nombres si el administrador entregó otros. La configuración de PostgreSQL
(`pg_hba.conf`) y los controles de red deben permitir a la VM web acceder a
`5432` y `6379`. El responsable de BD debe verificar también los permisos SQL y
ACL necesarios para el funcionamiento completo de la plataforma.

El Compose desactiva la creación automática de tablas y los datos de
demostración. Una base vacía no se prepara automáticamente. Consulta la
[guía de aplicación y migración del servidor de BD](https://github.com/lavillamarin3-hash/cociber-ctf-deploy/blob/main/docs/05_APLICACION_Y_MIGRACION.md)
con el responsable del laboratorio. No uses la base de Guacamole como base CTF.

## 3. Entrar al servidor web

En tu laptop Windows, abre **Inicio**, escribe **PowerShell** y ábrelo. Escribe
lo siguiente sustituyendo `USUARIO_UBUNTU` por tu usuario real:

```powershell
ssh USUARIO_UBUNTU@10.10.10.13
```

La primera conexión muestra una huella de identidad del servidor. Compárala con
la que confirme el administrador y acepta si coincide. Introduce tu contraseña:
es normal que no aparezcan letras ni asteriscos mientras la escribes.

**Desde ahora, los comandos de esta guía se ejecutan dentro de Ubuntu**, en esa
misma ventana. Copia un comando por vez y espera a que termine. Si aparece un
error, no continúes con el siguiente paso.

Comprueba que estás en el equipo correcto:

```bash
hostname
ip -br address
cat /etc/os-release
df -h /
```

Debes reconocer la VM web y la dirección `10.10.10.13/24`. El sufijo `/24` indica
la red: no se escribe en el navegador, en SSH ni en las URLs de conexión. Si la
IP no aparece, solicita corregir la red antes de iniciar Docker. La construcción
necesita espacio libre para imágenes y archivos temporales; no borres las VMs
que utilizas para conseguir espacio.

## 4. Preparar Git y Docker

Git descarga el código. Docker construye y ejecuta la aplicación.

```bash
sudo apt update
sudo apt install -y git curl ca-certificates nano
git --version
sudo docker --version
sudo docker compose version
```

Si Docker y Compose muestran una versión, conserva esa instalación. Si el
comando no existe, sigue la [instalación oficial de Docker Engine para Ubuntu](https://docs.docker.com/engine/install/ubuntu/),
en la sección de instalación mediante el repositorio `apt`. Incluye los paquetes
`docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin` y
`docker-compose-plugin`. La documentación oficial incluye Ubuntu 26.04. Si ya
hay otra instalación Docker, revisa sus instrucciones de compatibilidad antes
de sustituir paquetes.

Después de instalarlo:

```bash
sudo systemctl enable --now docker
sudo docker compose version
sudo docker info
```

Debes obtener información del servidor Docker sin errores de conexión.
Esta guía utiliza `sudo docker` para que no sea necesario modificar los grupos
del usuario. No instales paquetes de Python o Node en Ubuntu para resolver
dependencias de los contenedores: estas se declaran en los Dockerfiles.

## 5. Descargar el proyecto una sola vez

Si ya existe una copia operativa, utiliza su carpeta actual y omite la descarga.
No crees una segunda instalación encima de la existente. La ruta de ejemplo
para una instalación nueva es `/opt/ctf-platform`:

```bash
sudo install -d -o "$USER" -g "$(id -gn)" /opt/ctf-platform
git clone https://github.com/lavillamarin3-hash/ctf-platform.git /opt/ctf-platform
cd /opt/ctf-platform
git remote get-url origin
git branch --show-current
```

La dirección debe corresponder a `lavillamarin3-hash/ctf-platform` y la rama a
`main`. Si Git pide autenticación, utiliza el acceso que haya preparado el
administrador; no escribas contraseñas o tokens dentro de la URL del repositorio.

## 6. Preparar el archivo privado `.env`

`.env.example` es una plantilla pública. `.env` es el archivo privado con la
configuración real. **No reemplaces un `.env` que ya funciona por la plantilla.**

Solo si estás instalando por primera vez y todavía no existe `.env`:

```bash
umask 077
cp -n .env.example .env
chmod 600 .env
```

Para editar un archivo nuevo o uno existente:

```bash
nano .env
```

En Nano puedes moverte con las flechas y escribir normalmente. Guarda con
**Ctrl+O**, pulsa **Enter** y sal con **Ctrl+X**.

| Variable | Qué debes colocar |
| --- | --- |
| `WEB_BIND_IP` | `10.10.10.13`, dirección asignada al servidor web. |
| `WEB_PORT` | `80` si está disponible; conserva el puerto existente si hay otro proxy. |
| `DATABASE_URL` | Conexión a PostgreSQL CTF en `10.10.10.14:5432`. |
| `REDIS_URL` | Conexión a Redis CTF en `10.10.10.14:6379/0`. |
| `JWT_SECRET` | Secreto largo de autenticación. Conserva el valor existente al actualizar. |
| `FIELD_HMAC_SECRET` | Secreto usado para proteger datos de la aplicación. Conserva el valor existente. |
| `PUBLIC_ORIGIN` | Dirección exacta que usa el navegador, sin barra final. Ejemplo: `http://10.10.10.13`. |
| `MANAGE_SCHEMA_ON_STARTUP` | `false`; el usuario de ejecución no debe crear tablas. |
| `CTF_SEED_DEMO_DATA` | `false`; no introducir datos de demostración. |
| `GUACAMOLE_*` | Conserva todos los valores privados de la instalación operativa. |
| `FLAG_INJECTOR_*` | Conserva los valores, rutas y archivos SSH existentes si se utiliza el inyector. |

Ejemplos de formato; `CLAVE_PG_CODIFICADA` y `CLAVE_REDIS_CODIFICADA` se sustituyen
por las claves reales, nunca se dejan literalmente:

```dotenv
DATABASE_URL='postgresql+asyncpg://cociber_app:CLAVE_PG_CODIFICADA@10.10.10.14:5432/cociber_ctf?ssl=require'
REDIS_URL='redis://cociber_app:CLAVE_REDIS_CODIFICADA@10.10.10.14:6379/0'
```

Las contraseñas dentro de una URL necesitan codificación de caracteres
especiales: por ejemplo, `@` pasa a `%40` y `#` a `%23`. Solicita al administrador
las cadenas preparadas y conserva las comillas simples, que evitan que Compose
interprete un `$` como una variable. Nunca utilices una web pública para
transformar tus contraseñas.

El parámetro `ssl=require` de este backend con `asyncpg` requiere TLS en
PostgreSQL: cifra la comunicación, pero no verifica la identidad del servidor.
Si el laboratorio requiere verificación del certificado, el responsable debe
preparar el certificado CA dentro del contenedor, un nombre que coincida con el
certificado y la conexión `ssl=verify-full`. No cambies únicamente el texto sin
preparar esos requisitos. Redis utiliza la red privada con autenticación; usa
`rediss://` solamente cuando el servidor Redis tenga TLS configurado.

En una instalación nueva, puedes generar dos secretos diferentes ejecutando
dos veces el siguiente comando y copiando cada resultado en su variable:

```bash
openssl rand -hex 32
```

No regeneres secretos durante una actualización. Cambiar `JWT_SECRET` invalida
sesiones y cambiar `FIELD_HMAC_SECRET` puede impedir leer datos protegidos.

La plantilla conserva `GUACAMOLE_MODE=stub` y los demás valores de ejemplo
originales. Eso no configura una conexión real por sí solo. Traslada los valores
de tu instalación operativa; no alteres su servidor ni su base de datos.
Conserva también los montajes de claves SSH o certificados que utilice tu entorno.

Si se accede por `http://10.10.10.13:8081`, configura `WEB_PORT=8081` y
`PUBLIC_ORIGIN=http://10.10.10.13:8081`. Si ya existe un proxy HTTPS, conserva su
certificado, puerto y paso de WebSocket, y utiliza su dirección HTTPS como
`PUBLIC_ORIGIN`. Este Compose no instala certificados HTTPS; el puerto 80 del
ejemplo sirve HTTP dentro de la red del laboratorio.

## 7. Revisar una migración desde contenedores de BD antiguos

Este paso es necesario si anteriormente PostgreSQL o Redis se ejecutaban dentro
del Compose de la plataforma. Antes de cambiar la conexión, verifica que la
base externa contiene los datos correctos y el esquema compatible.

Quitar los servicios del archivo no migra los datos ni borra sus volúmenes. Docker
puede mostrar los contenedores anteriores como huérfanos. Consérvalos hasta que
el responsable confirme la migración. No ejecutes `down -v`,
`--remove-orphans` ni limpiezas de volúmenes como parte de esta guía.

Si existe `docker-compose.override.yml`, Compose lo puede cargar automáticamente.
Pide revisar que conserve únicamente los ajustes necesarios, como montajes SSH
o el proxy, y que no vuelva a introducir las bases locales ni las URLs antiguas.

## 8. Construir y arrancar

Sitúate en la carpeta del proyecto:

```bash
cd /opt/ctf-platform
sudo docker compose config --quiet
sudo docker compose config --services
```

El primer comando termina sin mostrar texto si la configuración es válida.
El segundo debe mostrar `api` y `web`. No uses `docker compose config` sin estas
opciones en capturas: puede mostrar las credenciales resueltas del `.env`.

Construye ambas imágenes. Esto descarga e instala las dependencias del backend
y compila la interfaz web; puede tardar varios minutos:

```bash
sudo docker compose build api web
```

Comprueba las conexiones utilizando la imagen recién construida:

```bash
sudo docker compose run --rm --no-deps api python -m app.check_services
```

Debes ver `PostgreSQL (lectura de users): OK` y `Redis (PING): OK`. El comando
solo lee una tabla y solicita una respuesta a Redis; no crea ni modifica datos.
Si aparece `ERROR`, detente y revisa con el administrador red, credenciales,
TLS, permisos y existencia de la tabla. Este control no valida todas las tablas
ni todas las operaciones de la aplicación.

Arranca y espera a que ambos contenedores respondan:

```bash
sudo docker compose up -d --force-recreate --wait --wait-timeout 180 api web
sudo docker compose ps
```

`-d` deja los servicios funcionando después de cerrar la terminal.
`--force-recreate` reemplaza los contenedores; al recrear ambos, Nginx vuelve a
resolver la dirección interna de la API. `--wait` espera su estado saludable.
Debes ver `api` y `web` en ejecución y con estado `healthy`.

El control de API comprueba PostgreSQL, Redis y HTTP. El de web comprueba Nginx.
Docker marca `unhealthy` cuando falla un control, pero ese estado por sí solo no
reinicia el contenedor. `restart: unless-stopped` actúa si el proceso termina.

## 9. Confirmar que funciona para los usuarios

```bash
sudo docker compose exec -T api python -m app.check_services --http
curl --fail http://10.10.10.13/api/v1/health
```

Adapta la URL si utilizas otro puerto o HTTPS. Debes ver los tres controles en
`OK` y una respuesta HTTP con `status` igual a `ok`. La ruta HTTP por sí sola no
comprueba las bases; por eso se utiliza también `check_services`.

Desde un navegador de la red del laboratorio:

1. Abre la dirección configurada, por ejemplo `http://10.10.10.13`.
2. Inicia sesión con una cuenta existente, no con una supuesta clave por defecto.
3. Comprueba que aparecen los usuarios, retos y puntuaciones esperados.
4. Abre el ranking y revisa su actualización en una práctica autorizada.
5. Prueba un reto que utilice Guacamole o el inyector, si forman parte del entorno,
   y cierra la sesión del laboratorio al terminar.

Si faltan datos que antes existían, revisa primero la base y el nombre de base
en `DATABASE_URL`. No actives datos de demostración para solucionar el problema.

Para consultar errores recientes:

```bash
sudo docker compose logs --tail=80 api web
```

Los registros pueden contener información privada: revísalos antes de compartirlos.
El Compose limita los registros Docker a tres archivos de 10 MB por servicio.

## 10. Cambios de esquema y permisos

En producción, Compose fuerza a `false` las opciones de crear esquema y de
cargar datos de demostración, incluso si un `.env` antiguo las deja en `true`.
No modifica el esquema ni crea una cuenta administradora al arrancar.

Una actualización que cambie tablas requiere instrucciones de migración propias
de esa versión y una copia recuperable de PostgreSQL. El repositorio no tiene un
flujo general de migraciones Alembic. Los scripts históricos situados en la raíz
de `backend/` tampoco se incluyen automáticamente en la imagen, que copia `app/`.
No ejecutes un comando de migración inventado ni actives la creación automática
para corregir columnas faltantes: `create_all` no es una migración completa.

La cuenta PostgreSQL de ejecución debe usar los permisos de datos necesarios.
Las operaciones de administración o migración se realizan con la cuenta y el
procedimiento que defina el responsable de BD. La base de Guacamole se mantiene
separada y no se utiliza para estas operaciones.

## 11. Problemas frecuentes

| Lo que observas | Qué hacer |
| --- | --- |
| `cannot assign requested address` | Confirma que `10.10.10.13` pertenece a la VM web; revisa `WEB_BIND_IP`. |
| `port is already allocated` | El puerto está ocupado. Si hay un proxy existente, conserva su diseño o acuerda otro puerto; no lo detengas a ciegas. |
| PostgreSQL muestra `ERROR` | Revisar `10.10.10.14:5432`, cuenta, clave codificada, TLS, `pg_hba.conf`, esquema y permiso de lectura. |
| Redis muestra `ERROR` | Revisar `10.10.10.14:6379`, usuario ACL, clave, permiso `PING` y red. |
| El arranque termina con tiempo agotado | Ejecutar `ps`, `check_services --http` dentro de API y consultar registros. Corregir la causa antes de repetir. |
| API responde, pero el navegador no carga | Revisar puerto publicado, proxy y acceso desde la red de usuarios. |
| WebSocket o ranking no conecta | Verificar que `PUBLIC_ORIGIN` coincide con la dirección del navegador y que el proxy permite WebSocket. |
| Los cambios del código no aparecen | Seguir la guía de actualización: descargar, construir y recrear ambos servicios. |
| Guacamole o SSH falla | Comparar su configuración privada y sus archivos montados con la instalación anterior. |
| La base está vacía o faltan columnas | Preparar o migrar la base mediante el procedimiento del responsable; no cargar ejemplos. |

Las reglas de acceso deben permitir la web desde las redes autorizadas y las BD
desde la VM web. Docker puede publicar puertos mediante reglas que evitan las de
UFW; el administrador debe aplicar la restricción en el lugar adecuado según la
[documentación de Docker sobre firewall](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

## 12. Comprobaciones para quien mantiene el código

La prueba unitaria del comprobador no necesita conectarse a la BD. Desde
`backend/`, en un entorno de desarrollo con Python compatible:

```bash
python -m unittest discover -s tests -p test_check_services.py -v
```

Las pruebas de integración de `backend/tests/` requieren un entorno de pruebas
preparado; no deben apuntarse a los datos reales de producción. Para comprobar
la compilación de la interfaz en desarrollo con Node 22, desde `frontend/`:

```bash
npm ci
npm run build
```

Estas comprobaciones complementan la construcción de imágenes y las pruebas
funcionales del paso 9; no las sustituyen.

## Referencias y siguiente tarea

- [Actualizar la plataforma desde GitHub](./GUIA_ACTUALIZAR_PRODUCCION.md).
- [Docker Engine en Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
- [Opciones oficiales de docker compose up](https://docs.docker.com/reference/cli/docker/compose/up/).
- [Dependencias y controles de salud de Compose](https://docs.docker.com/reference/compose-file/services/).
