"""Actualiza solo textos estándar antiguos; conserva objetivos y material del tutor."""

def update_text(text):
    if not text:
        return text
    replacements = {
        'Inicia una corrida y descarga el ZIP. Extrae los archivos y lee README.txt.':
            'Inicia una corrida y abre la terminal de Kali. Usa Copiar comando para preparar archivos, entra en ~/ctf/corrida-ID y lee README.txt.',
        'Usa herramientas locales; no necesitas una VM ni contactar hosts.':
            'Analiza las evidencias en Kali y consulta las pistas del reto cuando necesites orientación.',
        'Ejercicio descargable con datos sintéticos.': 'Ejercicio de análisis en Kali con datos sintéticos.',
        'También puedes resolverlo dentro de la VM Kali:': 'Resuelve el ejercicio dentro de la VM Kali:',
        'Inicia el caso y descarga las tres fuentes sintéticas.':
            'Inicia el caso y prepara las tres fuentes sintéticas en la terminal de Kali.',
        'Puedes usar herramientas locales para analizar los JSON.':
            'Utiliza las herramientas de Kali y las pistas del reto para analizar los JSON.',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text
