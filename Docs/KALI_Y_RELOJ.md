# Evidencias en Kali y reloj de los retos

La pantalla del estudiante ya no ofrece ZIP, adjuntos ni registros forenses
para analizar en el navegador. El alumno prepara las evidencias con el comando
de su corrida en Kali y trabaja en `~/ctf/corrida-ID`. Las pistas y los formularios
de validación siguen disponibles.

Los archivos del ejercicio, sus bytes originales y `SHA256SUMS.txt` se conservan
en el comando de preparación. En DFIR, `case.json` contiene el expediente y la
calibración de relojes. Los ejercicios que adquieren evidencias desde una VM con
herramientas de Kali mantienen ese funcionamiento. No se borran archivos de VM.

Se retiró la ruta `/api/v1/runs/{run_id}/offline/download`. Las vistas de caso
devuelven el objetivo y el comando de preparación; no incluyen adjuntos ni el
contenido de los registros como campos de presentación. Esto cambia el flujo
de la interfaz: no es una restricción de copia sobre los datos que recibe el alumno.

El reloj muestra horas, minutos y segundos, barra de tiempo restante y estados
de cinco minutos, último minuto y plazo finalizado. Usa el plazo original del
servidor: no reinicia la cuenta ni cambia las penalizaciones por pistas.

Para actualizar únicamente las frases estándar antiguas en la base existente:

```bash
python update_kali_instructions.py
python update_kali_instructions.py --apply
```

La primera orden muestra los códigos afectados. La segunda guarda los cambios
en una transacción y registra el texto anterior en auditoría. Conserva los
objetivos personalizados, flags, grupos, puntuación y evidencias.
