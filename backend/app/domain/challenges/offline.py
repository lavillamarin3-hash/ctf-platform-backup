"""Ejercicios sintéticos locales. Nunca incluir la respuesta privada en el bundle."""
import base64
import hashlib
import hmac
import io
import json
import random
import struct
import zipfile
import zlib

# code: (nombre honesto de la adaptación, familia, objetivo concreto)
CATALOG = {
    "003": ("Primera evidencia", "tree", "Localiza el valor evidence del archivo objetivo /practice/evidence.txt."),
    "115544": ("Filtrado de registros", "logs", "Identifica la sesión con result=success, role=admin y mfa=bypassed. Entrega su session."),
    "CRY-01": ("Base64 no es cifrado", "base64", "Decodifica el mensaje Base64 y entrega el texto UTF-8 resultante."),
    "CRY-02": ("XOR de una clave", "xor", "Recupera la clave XOR de un byte usando el prefijo conocido CTF: y entrega el texto que sigue al prefijo."),
    "CRY-03": ("RSA débil de práctica", "rsa", "Factoriza n, calcula la clave privada y descifra c. Entrega m como entero decimal. Parámetros pequeños solo para docencia."),
    "CRY-04": ("Hex y XOR", "hex_xor", "Convierte el hexadecimal a bytes, aplica XOR con la clave indicada y entrega el texto UTF-8."),
    "CTF-LNX-02": ("Explora un sistema de archivos exportado", "tree", "Localiza el valor evidence de /opt/ctf/flag.txt en la exportación de archivos."),
    "CTF-LNX-03": ("Reconoce SSH en una captura de servicios", "services", "Encuentra el puerto TCP en estado LISTEN del proceso sshd. Entrega solo el puerto decimal."),
    "ESC-02-BRUTEFORCE": ("Acceso inicial · análisis de intentos", "logs", "Entre los intentos sintéticos, identifica la sesión exitosa de administrador sin MFA (bypassed). Entrega session."),
    "ESC-03-WEBEXPLOIT": ("Incidente web · correlación local", "join", "Une los registros por request. Busca POST /admin/export con status=200 y destino 203.0.113.77. Entrega el request correlacionado."),
    "ESC-04-LATERAL": ("Movimiento lateral · eventos simulados", "lateral", "Une LogonId entre los eventos 4624 y 7045. Busca LogonType=3 desde WS-A a WS-B seguido de instalación del servicio update-agent. Entrega LogonId."),
    "ESC-05-EXFIL": ("Transferencia DNS · reconstrucción simulada", "dns_chunks", "Ordena por seq los fragmentos de consultas a transfer.example, concatena data y decodifica Base64. Entrega el texto recuperado."),
    "FOR-01": ("Metadatos reveladores", "metadata", "Inspecciona los chunks tEXt del PNG y entrega el valor del campo Case-ID."),
    "FOR-02": ("PCAP bajo la lupa", "pcap", "Abre la captura PCAP en Wireshark o analiza sus bytes. Recupera el texto después de evidence= en el datagrama UDP al puerto 9000."),
    "FOR-03": ("Memoria · muestra didáctica simulada", "memory", "Esta muestra binaria NO es un volcado real de Windows/Linux. Busca la cadena UTF-16LE CASE_ACTIVE= y entrega su valor hasta el terminador nulo."),
    "FOR-04": ("Evidencia de autenticación", "logs", "Encuentra la única sesión con autenticación exitosa, role=admin y mfa=bypassed. Entrega session."),
    "FOR-05": ("Integridad de artefactos", "integrity", "Compara los SHA-256 de los archivos con el manifiesto de adquisición. Entrega el nombre del único archivo modificado."),
    "LAB02": ("Tutorial de evidencias locales", "tutorial", "Lee la guía, calcula SHA-256 de evidence.txt (bytes exactos) y entrega el digest hexadecimal de 64 caracteres."),
    "MISC-01": ("Automatiza la reconstrucción", "chunks", "Ordena los fragmentos por seq, concatena data y decodifica Base64. Entrega el texto resultante."),
    "MISC-02": ("Archivo de evidencias", "tree", "Busca /var/archive/incident/evidence.txt y entrega su valor evidence."),
    "OSI-01": ("DNS de una organización ficticia", "dns", "En la zona ficticia encuentra el destino del CNAME portal.training.example; sigue su registro TXT y entrega el valor case."),
    "PWN-01": ("Ret2Win · análisis de pila simulado", "stack", "Simulación, sin ejecutable vulnerable: calcula el desplazamiento desde buffer hasta return_address y la dirección win. Entrega desplazamiento:dirección, por ejemplo 72:0x401234."),
    "RECON-02": ("Servicios expuestos · captura local", "services", "Analiza el inventario simulado y entrega el puerto TCP LISTEN del proceso sshd."),
    "REV-01": ("Strings en un binario didáctico", "strings", "Extrae cadenas ASCII de la muestra binaria (no es un ELF). Entrega el texto después de ACTIVE_EVIDENCE= hasta el byte nulo."),
    "REV-02": ("Invierte un validador", "validator", "Analiza validator.py, invierte su transformación y entrega la contraseña válida. No necesitas ejecutar código desconocido."),
    "REV-03": ("Cadena codificada", "hex_xor", "Convierte hex a bytes, invierte XOR con key y entrega el texto UTF-8."),
    "STE-01": ("Mensaje en los píxeles", "stego", "Lee el bit menos significativo de cada canal RGB en orden de filas (R,G,B), agrupando cada 8 bits de mayor a menor. El mensaje empieza por CTF: y termina en byte nulo. Entrega solo el texto entre ambos."),
    "WEB-01": ("Robots · sitio descargado", "robots", "Lee robots.txt y busca el archivo de la ruta Disallow en la copia del sitio. Entrega su campo evidence."),
    "WEB-02": ("Autenticación · revisión de código", "auth", "Revisa la condición de autenticación simulada. Elige la única solicitud que permite acceso admin con password_ok=false. Entrega su id."),
    "WEB-03": ("SQL · análisis de consultas", "sql", "En las consultas registradas identifica la que omite la contraseña mediante una condición OR siempre verdadera. Entrega su request_id. No hay servidor que atacar."),
    "WEB-04": ("Subidas · revisión de validaciones", "upload", "La política acepta solo PNG cuya firma sea 89504e470d0a1a0a. Identifica el registro aceptado por MIME que viola esa firma y entrega su id."),
    "WEB-05": ("HTTP · evidencia de una respuesta", "http", "Analiza la respuesta HTTP descargada. Decodifica el valor de la cabecera X-Evidence-Base64 y entrega el texto."),
    "WEB-06": ("Autorización de objetos · simulación", "idor", "Cruza solicitudes y propietarios. Identifica la solicitud con status=200 donde user no coincide con owner del object, excluyendo administradores. Entrega id."),
    "WIN-01": ("Windows · inventario exportado", "windows", "En el inventario simulado encuentra el equipo Windows con DomainJoined=true y BitLocker=false. Entrega ComputerName."),
    "WIN-02": ("Windows · procesos y servicios exportados", "process", "Une servicios y procesos por PID. Encuentra el servicio Running cuyo proceso está en C:\\Users\\Public\\update.exe y entrega el nombre del servicio."),
}


def _png(rgb, width, height, metadata=None):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    rows = b''.join(b'\0' + bytes(rgb[y*width*3:(y+1)*width*3]) for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
            + (chunk(b'tEXt', b'Case-ID\0' + metadata.encode()) if metadata else b'')
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def build_case(code, seed):
    title, kind, brief = CATALOG[code]
    rng = random.Random(seed)
    token = f'{rng.getrandbits(96):024x}'
    answer, raw = token, {}
    def add(name, data):
        raw[name] = data if isinstance(data, bytes) else data.encode('utf-8')
    def js(name, data):
        add(name, json.dumps(data, ensure_ascii=False, indent=2))
    if kind in ('base64', 'http'):
        encoded = base64.b64encode(token.encode()).decode()
        add('message.txt' if kind == 'base64' else 'response.http', encoded if kind == 'base64' else f'HTTP/1.1 200 OK\r\nX-Evidence-Base64: {encoded}\r\nContent-Length: 0\r\n\r\n')
    elif kind in ('xor', 'hex_xor'):
        key = rng.randrange(1, 256)
        plain = ('CTF:' if kind == 'xor' else '') + token
        js('cipher.json', {'hex': bytes(b ^ key for b in plain.encode()).hex(), **({'known_prefix': 'CTF:'} if kind == 'xor' else {'key': key})})
    elif kind == 'rsa':
        p, q = rng.choice([1009, 1013, 1019]), rng.choice([2003, 2011, 2017])
        m = rng.randrange(10000, 90000)
        answer = str(m)
        js('rsa.json', {'n': p*q, 'e': 65537, 'c': pow(m, 65537, p*q)})
    elif kind in ('chunks', 'dns_chunks'):
        encoded = base64.b64encode(token.encode()).decode()
        rows = [{'seq': i, 'data': encoded[i*4:i*4+4], **({'domain': 'transfer.example'} if kind == 'dns_chunks' else {})} for i in range(len(encoded)//4)]
        rng.shuffle(rows)
        if kind == 'dns_chunks':
            rows.append({'seq': 0, 'data': 'dGVz', 'domain': 'telemetry.example'})
        js('fragments.json', rows)
    elif kind == 'tree':
        target = {'003': 'practice/evidence.txt', 'CTF-LNX-02': 'opt/ctf/flag.txt', 'MISC-02': 'var/archive/incident/evidence.txt'}[code]
        for i in range(8): add(f'archive/old-{i}.txt', f'evidence=obsolete-{i}\n')
        add(target, f'evidence={token}\n')
    elif kind == 'logs':
        rows = [{'session': f's-{rng.getrandbits(64):016x}', 'result': 'success' if i%2 else 'failed', 'role': 'admin' if i%3 else 'reader', 'mfa': 'verified'} for i in range(30)]
        rows += [{'session': token, 'result': 'success', 'role': 'admin', 'mfa': 'bypassed'}, {'session': 'decoy', 'result': 'failed', 'role': 'admin', 'mfa': 'bypassed'}]
        rng.shuffle(rows); js('auth.json', rows)
    elif kind == 'join':
        http, net = [], []
        for i in range(15):
            key = token if i == 7 else f'r-{rng.getrandbits(64):016x}'
            http.append({'request': key, 'method': 'POST', 'path': '/admin/export', 'status': 200 if i % 2 else 403})
            net.append({'request': key, 'destination': '203.0.113.77' if i == 7 or i % 2 == 0 else '192.0.2.8'})
        rng.shuffle(http); rng.shuffle(net); js('http.json', http); js('network.json', net)
    elif kind == 'lateral':
        logins, services = [], []
        for i in range(12):
            key = token if i == 7 else f'0x{rng.getrandbits(32):08x}'
            logins.append({'EventID': 4624, 'LogonId': key, 'LogonType': 3 if i%2 else 2, 'source': 'WS-A', 'host': 'WS-B'})
            services.append({'EventID': 7045, 'LogonId': key, 'service': 'update-agent' if i == 7 or i%2 == 0 else 'approved-service', 'host': 'WS-B'})
        rng.shuffle(logins); rng.shuffle(services); js('logons.json', logins); js('services.json', services)
    elif kind == 'services':
        port = rng.randrange(2200, 6500); answer = str(port)
        js('sockets.json', [{'protocol': 'tcp', 'state': 'LISTEN', 'port': port, 'process': 'sshd'}, {'protocol': 'tcp', 'state': 'ESTABLISHED', 'port': 22, 'process': 'ssh'}, {'protocol': 'tcp', 'state': 'LISTEN', 'port': 8080, 'process': 'nginx'}])
    elif kind in ('metadata', 'stego'):
        rgb = [rng.randrange(256) for _ in range(32*32*3)]
        if kind == 'stego':
            bits = ''.join(f'{b:08b}' for b in ('CTF:' + token).encode() + b'\0')
            for i, bit in enumerate(bits): rgb[i] = (rgb[i] & 254) | int(bit)
        add('image.png', _png(rgb, 32, 32, token if kind == 'metadata' else None))
    elif kind in ('memory', 'strings'):
        data = ('CASE_ACTIVE=' + token + '\0').encode('utf-16le') if kind == 'memory' else ('ACTIVE_EVIDENCE=' + token + '\0').encode()
        add('sample.bin', rng.randbytes(300) + b'\0'*8 + data + b'\0'*8 + rng.randbytes(300))
    elif kind == 'pcap':
        payload = ('evidence=' + token).encode()
        udp = struct.pack('!4H', 42000, 9000, 8+len(payload), 0) + payload
        ip = bytearray(struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20+len(udp), 1, 0, 64, 17, 0, bytes([192,0,2,1]), bytes([192,0,2,2])))
        total = sum(struct.unpack('!10H', ip)); total = (total & 65535) + (total >> 16); total = (total & 65535) + (total >> 16)
        ip[10:12] = struct.pack('!H', (~total) & 65535)
        packet = bytes.fromhex('0200000000020200000000010800') + ip + udp
        add('capture.pcap', struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1) + struct.pack('<IIII', 1700000000, 0, len(packet), len(packet)) + packet)
    elif kind == 'integrity':
        manifest = {}; changed = rng.randrange(8); answer = f'artifact-{changed}.txt'
        for i in range(8):
            name = f'artifact-{i}.txt'; original = f'record={rng.getrandbits(96):024x}\n'.encode()
            manifest[name] = hashlib.sha256(original).hexdigest(); add(name, original + (b'altered\n' if i == changed else b''))
        js('acquisition.json', manifest)
    elif kind == 'tutorial':
        add('evidence.txt', token + '\n'); answer = hashlib.sha256(raw['evidence.txt']).hexdigest()
        add('guide.txt', 'Una evidencia conserva sus bytes, incluidos saltos de línea. En PowerShell: Get-FileHash evidence.txt -Algorithm SHA256. En Linux: sha256sum evidence.txt. Entrega solo el digest, después valida y registra los puntos.\n')
    elif kind == 'dns':
        alias = f'archive-{rng.randrange(100,999)}.training.example'
        js('zone.json', [{'name': 'portal.training.example', 'type': 'CNAME', 'value': alias}, {'name': alias, 'type': 'TXT', 'value': 'case='+token}, {'name': 'old.training.example', 'type': 'TXT', 'value': 'case=obsolete'}])
    elif kind == 'stack':
        offset = rng.choice([40, 56, 72, 88]); win = 0x401000 + 16*rng.randrange(10,100)
        answer = f'{offset}:{hex(win)}'
        js('stack.json', {'buffer_address': hex(0x7fff1000), 'return_address_slot': hex(0x7fff1000+offset), 'symbols': {'win': hex(win), 'main': '0x400900'}, 'architecture': 'x86_64 little endian', 'simulation_only': True})
    elif kind == 'validator':
        key = rng.randrange(1,256); target = [(b+key)%256 for b in token.encode()[::-1]]
        add('validator.py', f'# Validador didáctico puro; sin archivos, red ni comandos.\nTARGET = {target!r}\nKEY = {key}\ndef valid(text):\n    return [(b + KEY) % 256 for b in text.encode()[::-1]] == TARGET\n')
    elif kind == 'robots':
        path = f'private-{rng.randrange(10000,99999)}/evidence.json'
        add('site/robots.txt', f'User-agent: *\nDisallow: /{path}\n'); js('site/'+path, {'evidence': token})
    elif kind == 'auth':
        add('auth.py', 'def allowed(role, password_ok):\n    return password_ok or role == "admin"\n')
        js('requests.json', [{'id': token, 'role': 'admin', 'password_ok': False}, {'id': 'legitimate', 'role': 'admin', 'password_ok': True}, {'id': 'denied', 'role': 'reader', 'password_ok': False}])
    elif kind == 'sql':
        js('queries.json', [{'request_id': 'normal', 'sql': "SELECT id FROM users WHERE name='student' AND password='demo'"}, {'request_id': token, 'sql': "SELECT id FROM users WHERE name='' OR 1=1 -- ' AND password='wrong'"}, {'request_id': 'empty', 'sql': 'SELECT id FROM users WHERE 1=0'}])
    elif kind == 'upload':
        js('uploads.json', [{'id': 'valid', 'mime': 'image/png', 'accepted': True, 'signature': '89504e470d0a1a0a'}, {'id': token, 'mime': 'image/png', 'accepted': True, 'signature': '3c3f706870206563'}, {'id': 'blocked', 'mime': 'text/plain', 'accepted': False, 'signature': '68656c6c6f'}])
    elif kind == 'idor':
        js('objects.json', [{'id': 7, 'owner': 'alice'}, {'id': 8, 'owner': 'bob'}])
        js('requests.json', [{'id': token, 'user': 'alice', 'role': 'user', 'object': 8, 'status': 200}, {'id': 'own', 'user': 'alice', 'role': 'user', 'object': 7, 'status': 200}, {'id': 'admin', 'user': 'root', 'role': 'admin', 'object': 8, 'status': 200}, {'id': 'denied', 'user': 'bob', 'role': 'user', 'object': 7, 'status': 403}])
    elif kind == 'windows':
        answer = 'WS-' + token[:8]
        js('inventory.json', [{'ComputerName': answer, 'OS': 'Windows', 'DomainJoined': True, 'BitLocker': False}, {'ComputerName': 'WS-SAFE', 'OS': 'Windows', 'DomainJoined': True, 'BitLocker': True}, {'ComputerName': 'WS-HOME', 'OS': 'Windows', 'DomainJoined': False, 'BitLocker': False}])
    elif kind == 'process':
        answer = 'svc-' + token[:8]; pid = rng.randrange(1000,5000)
        js('services.json', [{'name': answer, 'PID': pid, 'status': 'Running'}, {'name': 'approved', 'PID': pid+1, 'status': 'Running'}])
        js('processes.json', [{'PID': pid+1, 'path': 'C:\\Windows\\System32\\svchost.exe'}, {'PID': pid, 'path': 'C:\\Users\\Public\\update.exe'}])
    else:
        raise ValueError('Familia no implementada')
    add('README.txt', f'{code} · {title}\n\n{brief}\n\nDatos sintéticos. Analiza estas evidencias dentro de Kali y consulta las pistas del reto. Python 3 permite analizar JSON, bytes y codificaciones. Para PNG/PCAP puedes usar un visor o analizador local.\nVuelve a la plataforma, valida tu respuesta y pulsa Registrar puntos. Los archivos y la respuesta cambian al iniciar otra corrida.\n')
    files = {name: base64.b64encode(data).decode() for name, data in raw.items()}
    return {'title': title, 'brief': brief, 'files': files, 'encoding': 'base64', 'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}}, answer


def matches_answer(expected, supplied):
    return hmac.compare_digest(expected.strip().casefold().encode(), supplied.strip().casefold().encode())


def archive(bundle):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for name, content in bundle['files'].items():
            zipped.writestr(name, base64.b64decode(content))
        zipped.writestr('SHA256SUMS.txt', '\n'.join(f'{digest}  {name}' for name, digest in bundle['sha256'].items()))
    return output.getvalue()
