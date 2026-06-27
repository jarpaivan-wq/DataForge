# DataForge — Changelog

---

## v3 — Schema Cache (2026-06-27)

### Nuevas funcionalidades
- **Caché de esquemas en disco**: después de inferir un esquema, se guarda automáticamente en `schemas/{key}.json`.
- **Reutilización inteligente**: al inicio de cada ejecución, DataForge detecta si existe un esquema cacheado para el dominio y pregunta al usuario si desea usarlo o regenerarlo.
- **Ahorro de tokens medido: 56%** (43,234 → 18,893 tokens) al evitar re-inferir esquemas grandes con muchas entidades.
- **Comando `limpiar caché`**: elimina todos los archivos `.json` de la carpeta `schemas/`.
- **Inyección de tool-calls sintéticos**: cuando el usuario elige usar el caché, se inyectan bloques `tool_use` + `tool_result` falsos en el array de mensajes para que Claude crea que ya ejecutó `leer_documento` e `inferir_esquema`, saltando directamente a `generar_csv`.

### Bugs resueltos
- **Cache bypass ignorado**: poner la instrucción "usa el caché" en el mensaje de texto no funcionaba — Claude seguía su `SYSTEM_PROMPT` y re-infería el esquema de todos modos. Solución: inyección sintética en el array `messages` (assistant turn con tool_use + user turn con tool_result).
- **`limpiar caché` no detectado en PowerShell**: el carácter `é` generaba mismatch de encoding al comparar strings. Solución: cambiar comparación exacta por `"limpiar" in user_input.lower() and "cach" in user_input.lower()`.

---

## v2 — Entity-Aware Schema (2026-06-27)

### Nuevas funcionalidades
- **Esquema por entidad**: `inferir_esquema` ya no devuelve rangos globales por columna sino rangos específicos por entidad (`entidades[].atributos`).
- **Detección automática de `entidad_principal`**: el agente identifica cuál columna representa la entidad dominante del dataset (e.g., `nombre_unidad`).
- **Variables biológicas**: instrucción fija añadida al mensaje del usuario para incluir `masa_corporal_kg`, `altura_cm`, `temperatura_corporal_celsius`, `frecuencia_cardiaca_bpm`, `capacidad_pulmonar_litros` con rangos inferidos por tamaño relativo de cada entidad.
- **Score de confianza por entidad**: campo `confianza: alta/media/baja` en cada entidad del esquema. Entidades con baja confianza reciben rangos conservadores (±20% del valor central).
- **Enriquecimiento con Wikipedia**: si el documento no tiene datos cuantitativos suficientes para una entidad, `inferir_esquema` consulta Wikipedia para complementar antes de marcar `confianza: baja`.
- **Temperatura dinámica**: `0.7` durante `inferir_esquema`, `0.5` durante `generar_csv`, `0.0` en el resto del loop.

### Bugs resueltos
- **Valores incoherentes entre entidades** (e.g., Zergling con 189 kg): los rangos globales mezclaban valores de entidades muy distintas. Solución: arquitectura entity-aware con rangos por entidad y lookup `entity_map` en `generar_csv`.
- **`nombre_unidad` mostrando `valor_X`**: el prompt de `inferir_esquema` no aplicaba la regla de usar `category` para listas finitas de entidades con nombre propio. Solución: regla explícita añadida al prompt del sistema.
- **`inferir_esquema` truncando JSON**: `max_tokens=4000` era insuficiente para esquemas de 20+ entidades. Solución: subir a `max_tokens=8000`.
- **`[Stop reason inesperado: max_tokens]` en el loop principal**: el JSON del esquema entity-aware es muy grande como tool_result; Claude necesitaba tokens para procesarlo y formular el siguiente tool_call. Solución: subir `MAX_TOKENS = 8000` en el loop principal.

---

## v1 — Agente Básico (2026-06-26)

### Funcionalidades iniciales
- **Agentic loop completo**: `while True` con `stop_reason == "tool_use"` / `"end_turn"` usando el SDK oficial de Anthropic.
- **Cuatro herramientas**: `leer_documento`, `buscar_wikipedia`, `inferir_esquema`, `generar_csv`.
- **Esquema global por columna**: rangos `{min, max}` sin distinción de entidad.
- **Soporte Windows SSL**: `truststore.inject_into_ssl()` para certificados corporativos.
- **Tracking de tokens**: acumulación de `input_tokens` + `output_tokens` con reporte al final de cada sesión.
- **Suite de tests con LLM-as-judge**:
  - 4 casos en `test_dataforge.py` (`@pytest.mark.integration`)
  - Test adversarial evalúa el rechazo de PII con `claude-haiku-4-5-20251001` a temperatura 0
  - Veredicto del juez (`esperado`, `profesional`, `razon`) impreso siempre con `pytest -s`

### Bugs resueltos
- **Test 1 sin CSV generado**: `inferir_esquema` tiene su propio `client.messages.create` interno; al mockear el loop principal, ese sub-call consumía el mock destinado a `generar_csv`, devolviendo `AttributeError`. Solución: parchear `TOOL_FUNCTIONS["inferir_esquema"]` con un fake que devuelve el schema JSON directamente.
- **`Unknown pytest.mark.integration` warning**: creado `pytest.ini` con registro del marcador.
