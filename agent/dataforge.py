import os
import sys
import io
import json
import csv
import random
import requests
import certifi
import httpx
import truststore
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv
import anthropic

# Inyecta el almacén de certificados de Windows en el módulo ssl
truststore.inject_into_ssl()

# Fuerza UTF-8 en stdout para que emojis y acentos no rompan en Windows
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 8000

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── Prompt del sistema (idéntico al original) ─────────────────────

SYSTEM_PROMPT = (
    "Eres DataForge, un agente especializado en generar \n"
    "bases de datos sintéticas realistas basadas en teoría \n"
    "y contexto real. Tu objetivo es ayudar a científicos, \n"
    "analistas y estudiantes a crear datos de prueba \n"
    "coherentes con la realidad de su dominio.\n\n"
    "<flujo_de_razonamiento>\n"
    "Ante cada solicitud de generación de datos, SIEMPRE \n"
    "sigue este orden:\n\n"
    "1. OBTENER CONTEXTO PRIMARIO\n"
    "   - Si el usuario proporcionó un archivo .md o .txt: \n"
    "     invoca leer_documento() primero.\n"
    "   - Si el usuario NO proporcionó archivo: \n"
    "     invoca buscar_wikipedia() con el dominio indicado.\n"
    "   - Nunca saltes este paso. Sin contexto no generas datos.\n\n"
    "2. SUPLEMENTAR CON WIKIPEDIA (condicional)\n"
    "   - Si leíste un documento PERO contiene poca información \n"
    "     cuantitativa (sin medidas, rangos numéricos, ni \n"
    "     comparaciones de magnitud entre entidades): \n"
    "     invoca también buscar_wikipedia() para obtener \n"
    "     datos numéricos adicionales del dominio.\n"
    "   - Combina el contexto del documento con el de Wikipedia \n"
    "     antes de llamar a inferir_esquema().\n"
    "   - Si el documento ya es suficientemente rico, omite este paso.\n\n"
    "3. INFERIR ESQUEMA\n"
    "   - Con el contexto obtenido (documento y/o Wikipedia), \n"
    "     invoca inferir_esquema().\n"
    "   - El esquema debe reflejar variables reales del dominio,\n"
    "     no columnas genéricas como 'campo1', 'campo2'.\n\n"
    "4. GENERAR DATOS\n"
    "   - Invoca generar_csv() con el esquema y el tamaño \n"
    "     solicitado por el usuario.\n"
    "   - Tamaños estándar: pequeño=50, mediano=500, grande=1000.\n"
    "   - Si el usuario no especifica tamaño, pregunta antes \n"
    "     de continuar.\n"
    "</flujo_de_razonamiento>\n\n"
    "<restricciones>\n"
    "- Nunca generes datos antes de tener contexto teórico.\n"
    "- Nunca inventes columnas sin respaldo en el contexto.\n"
    "- Nunca uses datos reales de personas o entidades.\n"
    "- Si Wikipedia no retorna resultados útiles, \n"
    "  infórmalo al usuario y pide un documento.\n"
    "</restricciones>\n\n"
    "<formato_de_respuesta>\n"
    "Al finalizar, responde siempre con:\n"
    "1. Nombre del archivo generado\n"
    "2. Número de registros\n"
    "3. Columnas creadas y por qué cada una existe \n"
    "   según la teoría\n"
    "4. Fuente del contexto usado (documento o Wikipedia)\n"
    "</formato_de_respuesta>"
)

# ── Definición de herramientas (idéntica al original) ─────────────

TOOLS = [
    {
        "type": "custom",
        "name": "generar_csv",
        "description": (
            "Genera un archivo CSV con datos sintéticos realistas basados en el esquema inferido. "
            "Úsala SIEMPRE como último paso, después de inferir_esquema(). Los datos deben respetar "
            "las distribuciones y rangos definidos en el esquema. Nunca la invoques sin un esquema "
            "previo. Tamaños estándar: pequeño=50 registros, mediano=500 registros, grande=1000 registros."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "esquema": {
                    "type": "string",
                    "description": "Esquema definido por inferir_esquema() con columnas, tipos y rangos de valores"
                },
                "nombre_archivo": {
                    "type": "string",
                    "description": "Nombre del archivo CSV a generar. Ejemplo: sismos_chile_500.csv"
                },
                "cantidad": {
                    "type": "integer",
                    "description": "Número de registros a generar. Valores estándar: 50 (pequeño), 500 (mediano), 1000 (grande)"
                }
            },
            "required": ["esquema", "nombre_archivo", "cantidad"]
        }
    },
    {
        "type": "custom",
        "name": "inferir_esquema",
        "description": (
            "Analiza el contexto teórico obtenido y define el esquema de la base de datos a generar. "
            "Úsala SIEMPRE después de obtener contexto, ya sea de leer_documento o buscar_wikipedia. "
            "Nunca la invoques sin contexto previo. Infiere columnas, tipos de datos y rangos de "
            "valores realistas basados en la teoría del dominio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contexto": {
                    "type": "string",
                    "description": "Texto con la teoría y conceptos clave obtenidos del documento o Wikipedia que guiarán la generación del esquema"
                },
                "descripcion_usuario": {
                    "type": "string",
                    "description": "Lo que el usuario describió que quiere generar. Ejemplo: tabla de sismos en Chile con magnitud y profundidad"
                }
            },
            "required": ["contexto", "descripcion_usuario"]
        }
    },
    {
        "type": "custom",
        "name": "leer_documento",
        "description": (
            "Lee un archivo .md o .txt proporcionado por el usuario y extrae su contenido como "
            "contexto teórico. Úsala SOLO cuando el usuario haya mencionado que tiene un archivo "
            "o lo haya subido. Tiene prioridad sobre buscar_wikipedia cuando ambas opciones estén disponibles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ruta_archivo": {
                    "type": "string",
                    "description": "Ruta completa al archivo .md o .txt proporcionado por el usuario. Ejemplo: /documentos/teoria_sismos.md"
                }
            },
            "required": ["ruta_archivo"]
        }
    },
    {
        "type": "custom",
        "name": "buscar_wikipedia",
        "description": (
            "Busca contexto teórico sobre un dominio en Wikipedia. Úsala SOLO cuando el usuario "
            "no haya proporcionado un archivo .md o .txt. Retorna definiciones, variables clave, "
            "distribuciones y relaciones entre entidades del dominio solicitado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dominio": {
                    "type": "string",
                    "description": "El tema o dominio sobre el cual buscar contexto teórico. Ejemplo: sismos Chile, paleontología dinosaurios, epidemiología COVID"
                }
            },
            "required": ["dominio"]
        }
    }
]


# ── Caché de esquemas ────────────────────────────────────────────

SCHEMAS_DIR = Path("schemas")

_current_cache_key: str | None = None  # seteado por run_dataforge antes del loop


def _cache_key(user_message: str) -> str:
    """Deriva un slug de caché desde el mensaje del usuario."""
    import re
    # Si hay ruta de archivo, usa el stem del nombre de archivo
    path_match = re.search(r'[\w/\\: ]+\.(txt|md)', user_message, re.IGNORECASE)
    if path_match:
        return Path(path_match.group().strip()).stem.lower().replace(" ", "_")
    # Si no, toma las primeras 4 palabras de 4+ letras
    words = re.findall(r'[a-záéíóúñA-ZÁÉÍÓÚÑ]{4,}', user_message)
    slug = "_".join(words[:4]).lower()
    return slug or "esquema"


def _load_cache(key: str) -> dict | None:
    """Lee un esquema cacheado. Retorna el dict o None si no existe."""
    path = SCHEMAS_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(key: str, schema_str: str, descripcion: str) -> None:
    """Persiste el esquema JSON en schemas/{key}.json con metadata."""
    SCHEMAS_DIR.mkdir(exist_ok=True)
    try:
        entry = {
            "key": key,
            "descripcion": descripcion,
            "timestamp": date.today().isoformat(),
            "esquema": json.loads(schema_str),
        }
        (SCHEMAS_DIR / f"{key}.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"[Caché]       Advertencia: no se pudo guardar — {e}")


# ── Implementaciones reales de las herramientas ───────────────────

WIKI_HEADERS = {
    "User-Agent": "DataForge/1.0 (jarpa.ivan@gmail.com) python-requests"
}

def buscar_wikipedia(dominio: str) -> str:
    """Consulta la Wikipedia en español y devuelve el extracto del artículo."""
    term = dominio.strip().replace(" ", "_")

    # Intento 1: resumen directo por título
    try:
        r = requests.get(
            f"https://es.wikipedia.org/api/rest_v1/page/summary/{term}",
            headers=WIKI_HEADERS, timeout=10
        )
        if r.status_code == 200:
            extract = r.json().get("extract", "")
            if len(extract) > 100:
                return extract
    except requests.RequestException:
        pass

    # Intento 2: búsqueda de texto y resumen del primer resultado
    try:
        r = requests.get(
            "https://es.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": dominio,
                "format": "json",
                "srlimit": 3,
            },
            headers=WIKI_HEADERS, timeout=10
        )
        if r.status_code == 200:
            results = r.json().get("query", {}).get("search", [])
            if results:
                title = results[0]["title"].replace(" ", "_")
                r2 = requests.get(
                    f"https://es.wikipedia.org/api/rest_v1/page/summary/{title}",
                    headers=WIKI_HEADERS, timeout=10
                )
                if r2.status_code == 200:
                    extract = r2.json().get("extract", "")
                    if extract:
                        return extract
    except requests.RequestException:
        pass

    return (
        f"No se encontró información útil en Wikipedia sobre '{dominio}'. "
        "Por favor, proporciona un archivo .md o .txt con el contexto teórico."
    )


def leer_documento(ruta_archivo: str) -> str:
    """Lee un archivo .md o .txt del disco y retorna su contenido."""
    path = Path(ruta_archivo)

    if not path.exists():
        return f"Error: el archivo '{ruta_archivo}' no existe en el sistema."

    if path.suffix.lower() not in [".md", ".txt"]:
        return (
            f"Error: solo se aceptan archivos .md y .txt. "
            f"El archivo tiene extensión '{path.suffix}'."
        )

    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error al leer el archivo: {e}"


def inferir_esquema(contexto: str, descripcion_usuario: str) -> str:
    """Llama a Claude (temp 0.7) para convertir el contexto en un JSON de esquema entity-aware."""
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            temperature=0.7,
            thinking={"type": "disabled"},
            system=(
                "Eres un experto en bases de datos. Dado un contexto teórico y una descripción, "
                "genera un JSON con el esquema entity-aware para una base de datos sintética.\n\n"

                "ESTRUCTURA OBLIGATORIA — responde SOLO con el JSON, sin texto adicional:\n"
                "{\n"
                '  "entidad_principal": "<nombre de la columna que identifica la entidad>",\n'
                '  "columnas": [\n'
                '    {"nombre":"...","tipo":"<TIPO>","min":...,"max":...,"opciones":[...],"descripcion":"..."}\n'
                "  ],\n"
                '  "entidades": [\n'
                '    {"valor":"<nombre entidad>","confianza":"alta|media|baja","atributos":{"<col_num>":{"min":X,"max":Y},...}}\n'
                "  ]\n"
                "}\n\n"

                "CAMPO entidad_principal:\n"
                "  Nombre de la columna cuyos valores son las entidades conocidas del documento "
                "(unidades, especies, personajes, lugares, etc.). Debe coincidir exactamente con "
                "el nombre de una columna de tipo 'category'.\n\n"

                "CAMPO columnas — entre 8 y 12 columnas. TIPOS DISPONIBLES:\n"
                "  float    → decimal. min y max son números reales. Ejemplo: masa_kg → min:0.5, max:300\n"
                "  integer  → entero. min y max son enteros. Ejemplo: bpm → min:40, max:200\n"
                "  date     → fecha. min/max en 'YYYY-MM-DD'. Ejemplo: min:'1960-01-01', max:'2024-12-31'\n"
                "  time     → hora. min/max en 'HH:MM:SS'. Ejemplo: min:'00:00:00', max:'23:59:59'\n"
                "  category → categórica. opciones: lista de 3-15 valores. min/max: null.\n"
                "  bool     → booleano. opciones: null. min/max: null.\n"
                "  string   → solo si ningún otro tipo aplica. Describe el patrón en 'descripcion'.\n\n"

                "CAMPO entidades:\n"
                "  Para CADA valor posible de entidad_principal (extráelos del documento), define:\n"
                "  - 'valor': nombre exacto de la entidad.\n"
                "  - 'confianza': nivel de certeza sobre los rangos inferidos:\n"
                "      'alta'  → el contexto contiene datos cuantitativos explícitos o comparaciones\n"
                "                directas de magnitud para esta entidad (medidas, estadísticas, tablas).\n"
                "      'media' → el contexto describe atributos cualitativos (grande, rápido, pesado)\n"
                "                que permiten inferir rangos relativos con moderada certeza.\n"
                "      'baja'  → información mínima o ausente; se usan rangos conservadores\n"
                "                (centrados en el rango global, con amplitud reducida al 30%).\n"
                "  - 'atributos': rangos específicos de TODAS las columnas de tipo float e integer.\n"
                "    No incluyas columnas de tipo category, bool, date, time o string.\n\n"
                "  REGLA DE RANGOS CONSERVADORES (confianza 'baja'):\n"
                "    Si no tienes datos suficientes para una entidad, calcula:\n"
                "      center = (global_min + global_max) / 2\n"
                "      half_range = (global_max - global_min) * 0.15\n"
                "      rango_conservador = {min: center - half_range, max: center + half_range}\n"
                "    Esto evita valores extremos cuando hay incertidumbre.\n\n"
                "REGLAS GENERALES:\n"
                "  - Nunca uses 'string' cuando puedes usar 'category', 'date', 'time', 'integer' o 'float'.\n"
                "  - Si el contexto tiene entidades con nombre propio finitas y conocidas, "
                "    úsalas como opciones de la columna entidad_principal (tipo category) "
                "    Y como valores en el array entidades.\n"
                "  - Los rangos en entidades deben reflejar las diferencias reales entre entidades "
                "    (ej: Ultralisk tiene masa_kg min:1000, max:5000; Zergling tiene min:15, max:40).\n"
                "  - El min/max global en columnas actúa como fallback; debe cubrir el rango total "
                "    de todas las entidades combinadas."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Contexto teórico:\n{contexto[:3000]}\n\n"
                    f"Descripción del usuario:\n{descripcion_usuario}"
                )
            }]
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        return raw
    except Exception as e:
        return f"Error al inferir esquema: {e}"


def _generar_valor(tipo, min_val, max_val, opciones):
    """Genera un valor aleatorio según tipo y rangos. Usado por generar_csv."""
    if tipo == "float":
        lo = float(min_val) if min_val is not None else 0.0
        hi = float(max_val) if max_val is not None else 100.0
        return round(random.uniform(lo, hi), 2)
    elif tipo in ("int", "integer"):
        lo = int(min_val) if min_val is not None else 0
        hi = int(max_val) if max_val is not None else 100
        return random.randint(lo, hi)
    elif tipo == "date":
        start = date.fromisoformat(str(min_val)) if min_val else date(2000, 1, 1)
        end = date.fromisoformat(str(max_val)) if max_val else date(2024, 12, 31)
        delta = max((end - start).days, 0)
        return (start + timedelta(days=random.randint(0, delta))).isoformat()
    elif tipo == "time":
        h_lo, m_lo, s_lo = [int(x) for x in (str(min_val or "00:00:00")).split(":")]
        h_hi, m_hi, s_hi = [int(x) for x in (str(max_val or "23:59:59")).split(":")]
        total_lo = h_lo * 3600 + m_lo * 60 + s_lo
        total_hi = h_hi * 3600 + m_hi * 60 + s_hi
        secs = random.randint(total_lo, total_hi)
        return f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
    elif tipo == "bool":
        return random.choice([True, False])
    elif tipo in ("str", "category", "string"):
        return random.choice(opciones) if opciones else f"valor_{random.randint(1, 1000)}"
    else:
        return f"valor_{random.randint(1, 1000)}"


def generar_csv(esquema: str, nombre_archivo: str, cantidad: int) -> str:
    """Parsea el JSON de esquema entity-aware y genera un CSV con datos sintéticos."""
    try:
        schema_data = json.loads(esquema)
        columnas = schema_data["columnas"]
    except (json.JSONDecodeError, KeyError) as e:
        return f"Error: esquema inválido. Esperaba JSON con clave 'columnas'. Detalle: {e}"

    if not columnas:
        return "Error: el esquema no contiene columnas."

    # Leer estructura entity-aware (opcional: esquemas legacy sin entidades siguen funcionando)
    entidad_principal = schema_data.get("entidad_principal")
    entidades_raw = schema_data.get("entidades", [])

    # Mapa: valor_entidad -> {nombre_columna -> {min, max}}
    # Mapa de confianza: valor_entidad -> "alta"|"media"|"baja"
    entity_map = {}
    confidence_map = {}
    for e in entidades_raw:
        if "valor" not in e:
            continue
        entity_map[e["valor"]] = e.get("atributos", {})
        confidence_map[e["valor"]] = e.get("confianza", "media")
    entity_values = list(entity_map.keys())

    # Generar filas
    rows = []
    for _ in range(cantidad):
        # Elegir entidad primero (si hay mapa de entidades)
        chosen_entity = random.choice(entity_values) if entity_values else None
        entity_attrs = entity_map.get(chosen_entity, {}) if chosen_entity else {}

        row = {}
        for col in columnas:
            nombre = col.get("nombre", "columna")
            tipo = col.get("tipo", "str")
            opciones = col.get("opciones")

            # La columna entidad_principal toma el valor de la entidad elegida
            if nombre == entidad_principal and chosen_entity is not None:
                row[nombre] = chosen_entity
                continue

            # Rangos: usa los de la entidad si existen, si no el global de la columna
            if nombre in entity_attrs:
                min_val = entity_attrs[nombre].get("min")
                max_val = entity_attrs[nombre].get("max")
            else:
                min_val = col.get("min")
                max_val = col.get("max")

            try:
                row[nombre] = _generar_valor(tipo, min_val, max_val, opciones)
            except (ValueError, TypeError):
                row[nombre] = None

        rows.append(row)

    # Guardar CSV
    try:
        path = Path(nombre_archivo)
        col_names = [c.get("nombre", f"col_{i}") for i, c in enumerate(columnas)]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=col_names)
            writer.writeheader()
            writer.writerows(rows)

        # Resumen de confianza: cuenta entidades por nivel
        confianza_resumen = {"alta": 0, "media": 0, "baja": 0}
        for nivel in confidence_map.values():
            if nivel in confianza_resumen:
                confianza_resumen[nivel] += 1
        entidades_baja = [v for v, c in confidence_map.items() if c == "baja"]

        return json.dumps({
            "archivo": str(path.resolve()),
            "registros": cantidad,
            "columnas": col_names,
            "confianza_resumen": confianza_resumen,
            "entidades_confianza_baja": entidades_baja,
        }, ensure_ascii=False)
    except Exception as e:
        return f"Error al guardar el CSV: {e}"


# ── Dispatcher ────────────────────────────────────────────────────

TOOL_FUNCTIONS = {
    "buscar_wikipedia": buscar_wikipedia,
    "leer_documento": leer_documento,
    "inferir_esquema": inferir_esquema,
    "generar_csv": generar_csv,
}


def ejecutar_herramienta(nombre: str, inputs: dict) -> str:
    fn = TOOL_FUNCTIONS.get(nombre)
    if not fn:
        return f"Error: herramienta '{nombre}' no reconocida."
    try:
        result = fn(**inputs)
        if nombre == "inferir_esquema" and _current_cache_key and not result.startswith("Error"):
            _save_cache(
                _current_cache_key,
                result,
                inputs.get("descripcion_usuario", ""),
            )
            print(f"[Caché]       Esquema guardado → schemas/{_current_cache_key}.json")
        return result
    except TypeError as e:
        return f"Error en argumentos de '{nombre}': {e}"


# ── Temperatura dinámica ──────────────────────────────────────────

def get_temperature(last_tool) -> float:
    """
    Temperatura 0 para las fases de búsqueda e inferencia.
    Temperatura 0.3 para la fase de generación de datos (tras inferir_esquema),
    ya que aporta variabilidad realista a los valores generados.
    """
    return 0.5 if last_tool == "inferir_esquema" else 0.0


# ── Loop agentico principal ───────────────────────────────────────

BIOLOGICAL_VARIABLES_INSTRUCTION = (
    "\n\nIncluye variables biológicas medibles como: "
    "masa_corporal_kg, altura_cm, temperatura_corporal_celsius, "
    "frecuencia_cardiaca_bpm, capacidad_pulmonar_litros. "
    "Infiere rangos realistas basados en el tamaño relativo "
    "de cada unidad descrito en el documento."
)

def run_dataforge(user_message: str) -> None:
    global _current_cache_key

    SCHEMAS_DIR.mkdir(exist_ok=True)
    key = _cache_key(user_message)
    _current_cache_key = key

    print(f"\n{'='*60}")
    print("DataForge iniciado")
    print(f"{'='*60}\n")

    # ── Verificar caché ───────────────────────────────────────────
    full_message = user_message + BIOLOGICAL_VARIABLES_INSTRUCTION
    messages = [{"role": "user", "content": full_message}]  # default: pipeline completo
    last_tool_called = None

    cached = _load_cache(key)
    if cached:
        print(f"[Caché] Esquema encontrado: schemas/{key}.json")
        print(f"        Dominio    : {cached.get('descripcion', '(sin descripción)')[:80]}")
        print(f"        Guardado   : {cached.get('timestamp', '?')}")
        respuesta = input("        ¿Usar esquema guardado? [S = sí / N = regenerar]: ").strip().lower()
        if respuesta in ("s", "si", "sí", "y", "yes", ""):
            schema_str = json.dumps(cached["esquema"], ensure_ascii=False)
            # Inyectamos tool calls sintéticos: Claude "cree" que ya ejecutó
            # leer_documento e inferir_esquema y pasará directo a generar_csv.
            fake_tool_id_doc    = "toolu_cache_doc"
            fake_tool_id_schema = "toolu_cache_schema"
            messages = [
                {"role": "user", "content": full_message},
                {"role": "assistant", "content": [
                    {"type": "tool_use", "id": fake_tool_id_doc,
                     "name": "leer_documento",
                     "input": {"ruta_archivo": "(cargado desde caché)"}},
                    {"type": "tool_use", "id": fake_tool_id_schema,
                     "name": "inferir_esquema",
                     "input": {"contexto": "(cargado desde caché)",
                               "descripcion_usuario": cached.get("descripcion", "")}},
                ]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": fake_tool_id_doc,
                     "content": "Documento cargado desde caché."},
                    {"type": "tool_result", "tool_use_id": fake_tool_id_schema,
                     "content": schema_str},
                ]},
            ]
            last_tool_called = "inferir_esquema"  # activa temp 0.5 para generar_csv
            print("[Caché] Usando esquema guardado — saltando inferencia.\n")
        else:
            print("[Caché] Regenerando esquema desde el contexto.\n")

    total_input_tokens = 0
    total_output_tokens = 0

    while True:
        temp = get_temperature(last_tool_called)

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=temp,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            thinking={"type": "disabled"},
            messages=messages,
        )

        total_input_tokens  += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Agregar turno del asistente al historial
        messages.append({"role": "assistant", "content": response.content})

        # ¿Terminó la conversación?
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print("\n" + block.text)
            print(f"\n{'─'*60}")
            print(f"[Tokens] Input: {total_input_tokens:,}  |  Output: {total_output_tokens:,}  |  Total: {total_input_tokens + total_output_tokens:,}")
            print(f"{'─'*60}")
            break

        if response.stop_reason != "tool_use":
            print(f"\n[Stop reason inesperado: {response.stop_reason}]")
            print(f"[Tokens] Input: {total_input_tokens:,}  |  Output: {total_output_tokens:,}  |  Total: {total_input_tokens + total_output_tokens:,}")
            break

        # Procesar cada tool call del turno
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            last_tool_called = tool_name

            print(f"\n[Herramienta] {tool_name}")
            preview = json.dumps(tool_input, ensure_ascii=False)
            print(f"[Input]       {preview[:300]}{'...' if len(preview) > 300 else ''}")

            result = ejecutar_herramienta(tool_name, tool_input)

            print(f"[Output]      {result[:300]}{'...' if len(result) > 300 else ''}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        # Devolver resultados como turno de usuario
        messages.append({"role": "user", "content": tool_results})


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("    DataForge — Generador de Bases de Datos Sintéticas")
    print("=" * 60)
    print("Ejemplos de uso:")
    print("  'Quiero generar una base de datos de sismos en Chile, tamaño mediano.'")
    print("  'Genera datos de epidemiología de COVID-19, tamaño pequeño.'")
    print("  'Crea una base de datos de volcanes activos, tamaño grande.'")
    print("=" * 60 + "\n")

    try:
        user_input = input("DataForge > ").strip()
        if not user_input:
            print("Error: ingresa una descripción de los datos a generar.")
        elif "limpiar" in user_input.lower() and "cach" in user_input.lower():
            if SCHEMAS_DIR.exists():
                archivos = list(SCHEMAS_DIR.glob("*.json"))
                for f in archivos:
                    f.unlink()
                print(f"Caché limpiado: {len(archivos)} esquema(s) eliminado(s).")
            else:
                print("No hay caché que limpiar.")
        else:
            run_dataforge(user_input)
    except KeyboardInterrupt:
        print("\n\nDataForge interrumpido.")
