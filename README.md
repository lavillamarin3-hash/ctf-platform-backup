# Cociber CTF — Entrenamiento en Ciberseguridad

## Despliegue de producción

Este repositorio prepara la plataforma para **Ubuntu Server 26.04** con las bases
de datos instaladas de forma nativa en una máquina virtual independiente:

| Máquina | Dirección | Función |
| --- | --- | --- |
| Servidor web | `10.10.10.13/24` | Docker Compose: interfaz web/Nginx y API FastAPI. |
| `LAB-DB-POSTGRES` | `10.10.10.14` | PostgreSQL en `5432` y Redis en `6379`, instalados de forma nativa. |
| Apache Guacamole | Configuración existente | Servicio y base de datos independientes; se conservan. |

Empieza por la [guía de instalación paso a paso](./README-SETUP.md). Para una
plataforma que ya funciona, utiliza la [guía sencilla de actualización desde
GitHub](./GUIA_ACTUALIZAR_PRODUCCION.md), que incluye comprobación y recuperación.

## Descripción

Cociber CTF es una plataforma web de entrenamiento en ciberseguridad con experiencia estilo CTF
(Capture The Flag), diseñada para un laboratorio académico. Permite que los
estudiantes resuelvan retos asociados a escenarios de ataque, envíen flags y
reciban una validación, puntuación y seguimiento de su progreso.

La plataforma es la capa de entrenamiento, interacción y evaluación del
laboratorio. **No reemplaza a Security Onion ni es el mecanismo de detección**:
Security Onion conserva sus funciones de monitoreo y detección.

## Objetivos

- Proporcionar un entorno controlado para practicar escenarios de ataque.
- Relacionar los retos con técnicas de MITRE ATT&CK y distintos niveles de
  dificultad.
- Validar flags y registrar los intentos de los jugadores.
- Medir el avance mediante puntuación, progreso y ranking.
- Facilitar a los instructores la organización de retos y a los estudiantes el
  acceso a las máquinas víctima autorizadas.

## Características principales

- Autenticación y control de acceso basado en roles (RBAC).
- Gestión de usuarios.
- Gestión de retos.
- Definición y validación de flags.
- Registro de intentos.
- Ranking y progreso del jugador.
- Filtrado de retos por dificultad.
- Filtrado por técnica MITRE ATT&CK.
- Instrucciones de acceso a máquinas víctima.
- Actualización del ranking en tiempo real.
- Exportación de reportes y del ranking.

## Niveles de dificultad

La dificultad representa la complejidad del reto y determina su puntuación:

| Nivel | Puntos |
| --- | ---: |
| Básico | 100 |
| Medio | 250 |
| Avanzado | 500 |

## Escenarios CTF

Los escenarios agrupan retos relacionados con una técnica MITRE ATT&CK, una
dificultad y una o más máquinas víctima del laboratorio. Las flags se validan
como parte del flujo de resolución del reto.

| Escenario | Técnica MITRE ATT&CK | Dificultad | VM(s) víctima | Flags |
| --- | --- | --- | --- | --- |
| `ESC-01-RECON` | T1046 — Network Service Scanning | Básico | `LAB-LNXVICT`, `LAB-SRVWEB` | Flags de reconocimiento |
| `ESC-02-BRUTEFORCE` | T1110.001 — Password Guessing | Medio | Máquinas víctima del laboratorio | Flags de fuerza bruta |
| `ESC-03-WEBEXPLOIT` | T1190 — Exploit Public-Facing Application | Medio | `LAB-SRVWEB` | Flags de explotación web |
| `ESC-04-LATERAL` | T1021.002 — SMB/Windows Admin Shares | Avanzado | `LAB-LNXVICT` | Flags de movimiento lateral |
| `ESC-05-EXFIL` | T1048 — Exfiltration Over Alternative Protocol | Avanzado | Máquinas víctima del laboratorio | Flags de exfiltración |

Las instrucciones de cada reto delimitan el alcance de las actividades y los
activos autorizados. Las flags concretas pertenecen a la configuración del
reto y no se documentan en este archivo.

## Laboratorio web Operación Cóndor

[Operación Cóndor tiene su propio repositorio](https://github.com/lavillamarin3-hash/operacion-condor). Es un portal ficticio para practicar reconocimiento web, correlación de cuentas y comprobación de credenciales con un diccionario acotado. En la modalidad SSH, el reto `WEB-CONDOR` integra la terminal de Kali, el tiempo, las pistas y la validación de la flag en Cociber CTF. El estudiante investiga la IP y los puertos asignados, encuentra el usuario y la contraseña del laboratorio y publica un comunicado con título libre para obtener la flag. Debe conservar evidencias y explicar sus hallazgos al tutor. La web es independiente y compartida: iniciar o cerrar el reto no aprovisiona VMs ni reinicia sus datos. Consulta la [guía del estudiante](./Docs/GUIA_OPERACION_CONDOR.md).

## Roles

El control de acceso utiliza **RBAC (Role-Based Access Control)**.

| Rol | Responsabilidades |
| --- | --- |
| Administrador | Gestionar usuarios, roles y la configuración general de la plataforma. |
| Instructor / Diseñador de retos | Diseñar, gestionar y publicar retos, flags e instrucciones. |
| Jugador (Estudiante) | Consultar retos, acceder al laboratorio autorizado, enviar flags y revisar su progreso y posición. |
| Invitado (opcional) | Consultar el contenido que la configuración permita sin participar en la evaluación. |

## Arquitectura

La plataforma utiliza **Arquitectura Hexagonal (Ports & Adapters)** para
separar las reglas del dominio de la infraestructura:

- **Núcleo de dominio:** entidades y reglas de retos, flags, puntuación,
  progreso y ranking.
- **Casos de uso:** autenticación, gestión de retos, validación de flags,
  registro de intentos, actualización del ranking y gestión del acceso a
  máquinas víctima.
- **Puertos:** contratos que el núcleo utiliza para persistencia, publicación
  de eventos y acceso al laboratorio.
- **Adaptadores:** API HTTP, interfaz web, base de datos, comunicación en
  tiempo real y acceso remoto al laboratorio.
- **Persistencia:** almacenamiento de usuarios, retos, flags, intentos,
  progreso y resultados.
- **Comunicación en tiempo real:** publicación de cambios para mantener
  actualizado el ranking.

```mermaid
flowchart LR
    UI[Frontend web] --> HTTP[Adaptador HTTP / API]
    HTTP --> UC[Casos de uso]
    UC --> D[ Nucleo de dominio ]
    UC --> P[(Puertos)]
    P --> DB[Adaptador de persistencia]
    DB --> DATA[(Base de datos)]
    P --> RT[Adaptador tiempo real]
    RT --> WS[Clientes suscritos]
    P --> LAB[Adaptador de acceso al laboratorio]
    LAB --> VM[Maquinas victima]
```

Security Onion permanece fuera de este flujo como componente de monitoreo y
detección del laboratorio.

## Patrones de diseño

- **Strategy:** permite encapsular y seleccionar la estrategia de validación
  de flags o de resolución de un reto.
- **Repository:** abstrae el acceso a usuarios, retos, flags, intentos y
  resultados persistidos.
- **Observer / Publicador-Suscriptor:** comunica cambios del ranking a los
  clientes conectados en tiempo real.
- **Factory:** centraliza la creación de adaptadores y objetos de ejecución
  según la configuración del entorno.

## Stack tecnológico

| Componente | Tecnología |
| --- | --- |
| Backend | Python + FastAPI |
| Frontend | React + TypeScript + TailwindCSS |

Docker Compose construye el backend y el frontend, con sus dependencias dentro
de las imágenes. PostgreSQL y Redis se consumen desde `LAB-DB-POSTGRES`; este
Compose no crea bases de datos ni administra Apache Guacamole.

## Ejecución general

### Requisitos

- Docker Engine y Docker Compose en el servidor web.
- Un archivo privado `.env`, basado en [`.env.example`](./.env.example).
- Acceso de red a las bases de datos externas, cuentas de aplicación y una base
  CTF con el esquema compatible y usuarios ya preparados.

### Inicio

1. En una instalación nueva, copia `.env.example` como `.env`. En una
   actualización, conserva el `.env` existente y sus secretos.
2. Configura las credenciales reales de PostgreSQL y Redis en `10.10.10.14`.
   Conserva los valores operativos de `GUACAMOLE_*` y del inyector SSH.
3. Desde la carpeta del proyecto, ejecuta cada comando por separado. Si uno
   falla, resuelve el error antes de continuar:

   ```bash
   sudo docker compose config --quiet
   sudo docker compose build api web
   sudo docker compose run --rm --no-deps api python -m app.check_services
   sudo docker compose up -d --force-recreate --wait --wait-timeout 180 api web
   sudo docker compose ps
   ```

4. Abre `http://10.10.10.13` con la configuración de ejemplo. Si existe un proxy
   HTTPS o se utiliza otro puerto, abre la dirección real y configura
   `PUBLIC_ORIGIN` exactamente igual, sin barra final.

El backend comprueba lectura de la tabla `users` en PostgreSQL, `PING` en Redis
y su respuesta HTTP antes de que arranque el frontend. Esta comprobación no
sustituye probar el inicio de sesión, los retos y Guacamole. El puerto `8000`
queda dentro de la red Docker; el proxy web publica `/api/` y no publica `/docs`.

En producción, Compose fuerza `MANAGE_SCHEMA_ON_STARTUP=false` y
`CTF_SEED_DEMO_DATA=false`: no crea tablas, usuarios ni datos de demostración al
iniciar. Una base vacía necesita preparación o migración antes del despliegue.

## Relación con el laboratorio

La plataforma entrega el contexto de los retos, las instrucciones y el acceso
controlado a las máquinas víctima. El laboratorio conserva la separación entre
los activos de entrenamiento y el monitoreo. Las actividades de los jugadores
deben limitarse a los escenarios y activos autorizados por el instructor.

## Documentación adicional

- [Instalación y configuración en Ubuntu Server 26.04](./README-SETUP.md)
- [Actualizar producción desde GitHub, paso a paso](./GUIA_ACTUALIZAR_PRODUCCION.md)
- [Configuración de entorno](./.env.example)
- [Backend](./backend/)
- [Frontend](./frontend/)
- [Configurar tiempo, pistas y descuentos por reto](./Docs/CONFIGURAR_TIEMPO_Y_PISTAS.md)
- [Retos de investigación con Kali y LNX-VICT](./Docs/RETOS_VM_LOGICA.md)
- [Resolver Operación Cóndor en la demostración local](./Docs/GUIA_OPERACION_CONDOR.md)
- [Eliminar un reto definitivamente](./Docs/ELIMINAR_RETOS.md)
- Documentación interactiva de la API: `/docs` en la API interna; no se expone por el proxy de producción.


## Fase A — banderas dinámicas

La base de implementación se documenta en [Fase A](./Docs/FASE_A_BANDERAS_DINAMICAS.md).
El inyector SSH está deshabilitado por defecto y requiere configuración por
variables de entorno.
