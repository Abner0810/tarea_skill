---
name: control-gastos
description: Clasifica gastos personales en cuatro categorias (servicios, comida, ropa y otros) a partir de un CSV y genera un resumen mensual con totales, porcentajes y subcategorias. Usa cuando el usuario pida organizar, revisar, resumir o controlar gastos, cuentas, gastos del mes, compras, presupuesto semanal, o cuando tenga un CSV de compras y quiera saber en que se le va el dinero.
license: MIT
compatibility: Requiere Python 3.10 o superior. La salida CSV no necesita dependencias externas; la salida .xlsx requiere openpyxl>=3.1.0. Funciona en Windows, Linux y macOS.
metadata:
  author: abner-barrenechea
  version: "1.1"
  category: productividad-finanzas
---

# Control de Gastos

Toma un CSV de compras, clasifica cada gasto en una de cuatro categorias y devuelve un
resumen con totales y porcentajes, mas la lista de gastos que necesita revision manual.

## Instalación y rutas

La skill se instala copiando esta carpeta a la carpeta de skills del agente. La ruta universal es
`~/.agents/skills/control-gastos/`, que leen de forma nativa Codex, Cursor, Gemini CLI, OpenCode,
GitHub Copilot y VS Code. La unica excepcion es Claude Code, que usa `~/.claude/skills/`. La tabla
completa de rutas por agente esta en el README.

En Windows, `~` es `%USERPROFILE%`.

No asumas que el directorio de trabajo actual es la carpeta de la skill. Usa siempre la ruta
absoluta al ejecutar:

```bash
python "~/.agents/skills/control-gastos/scripts/gastos.py" <ruta-del-csv-del-usuario>
```

El script resuelve su diccionario de reglas (`assets/categorias.json`) a partir de su propia
ubicación, así que funciona desde cualquier directorio. Para la demostración:

```bash
python "~/.agents/skills/control-gastos/scripts/demo.py"
```

Todas las rutas citadas más abajo en este documento son relativas a la carpeta de la skill.
Sustitúyelas por la ruta de instalación cuando ejecutes comandos.

## Dependencia para salida XLSX

La salida CSV funciona sin instalar paquetes. Para generar un archivo `.xlsx` real, instala la
dependencia incluida antes de ejecutar el comando:

```bash
python -m pip install -r "~/.agents/skills/control-gastos/assets/requirements-xlsx.txt"
```

La dependencia es `openpyxl>=3.1.0`. Si se solicita `.xlsx` sin tenerla instalada, el script termina
con codigo `3` e indica el comando de instalación. La salida por defecto sigue siendo CSV.

## Cuando usar

- El usuario pide organizar o resumir sus gastos del mes, semana o quincena.
- El usuario tiene un CSV o una lista de compras y quiere saber en que se le va el dinero.
- El usuario pide un presupuesto basado en categorias (servicios, comida, ropa, otros).
- El usuario quiere revisar si un gasto en particular quedo bien clasificado.

No usar para: conciliar facts de banco con movimientos bancarios, proyectar ingresos, ni
cualquier cosa que requiera datos que no esten en el archivo de entrada.

## Principios

1. **Cuatro categorias, ni una mas.** Servicios, comida, ropa y otros. La simplicidad de la
   clasificacion es parte del producto, no una limitacion.
2. **Ninguna entrada rompe el flujo.** Si una compra no se reconoce, va a `otros` con la
   etiqueta `sin_clasificar` y aparece en la seccion REVISAR. El script nunca adivina.
3. **Errores claros y acumulativos.** Se reportan todos los problemas de una vez, con numero
   de fila y valor culpable, en vez de fallar en el primero.
4. **Determinista y explicable.** Misma entrada, mismo resultado, siempre. Sin IA, sin API, sin
   claves. El usuario puede ver que palabra clave decido cada gasto con `--detalle`.
5. **Reglas en datos, no en codigo.** Las palabras clave viven en `assets/categorias.json`.
   Extender el skill es editar un archivo, no programar.

## Las cuatro categorias

| Categoria | Que entra | Subcategorias tipicas |
| --- | --- | --- |
| `servicios` | Servicios recurrentes del hogar | luz, agua, gas, internet, telefonia |
| `comida` | Todo lo que se consume | supermercado, panaderia, restaurante, delivery, cafeteria |
| `ropa` | Vestimenta, calzado y accesorios | ropa, calzado, accesorios |
| `otros` | Todo lo que no entra en las 3 anteriores | transporte, salud, ocio, educacion, hogar, sin_clasificar |

## Flujo de trabajo

1. **Detectar el formato**: el separador de columnas se detecta solo (`,` o `;`) leyendo la
   cabecera, y los nombres de columna se normalizan a minusculas sin acentos, admitiendo
   sinonimos (`Importe` = `monto`, `Concepto` = `descripcion`).
2. **Validar la cabecera**: exige `fecha`, `descripcion`, `monto`. Acepta `categoria` como
   opcional. Rechaza columnas desconocidas.
3. **Normalizar cada fila**: fecha a formato ISO, monto a float (acepta `45.00`, `"45,00"`,
   `45,00` y `Bs 45`), descripcion sin acentos ni signos para poder buscar palabras.
4. **Clasificar**: si la fila trae `categoria`, se respeta. Si no, se busca la palabra clave
   mas larga que coincida; gana la coincidencia mas especifica.
5. **Agrupar y calcular**: total por categoria y por subcategoria, con porcentaje sobre el total.
6. **Reportar**: imprime tabla en consola y escribe un CSV o un libro `.xlsx` segun la extension de
   `-o`. Los gastos sin regla explicita quedan listados para revision.

## Ejemplos de entrada y salida esperada

| Entrada del usuario | Accion esperada |
| --- | --- |
| "Aqui esta mi CSV del mes, clasificalo" | Valida, clasifica solo, imprime tabla y genera `resumen.csv`; con `-o salida.xlsx` genera un libro organizado |
| "Muestrame en que me voy la plata" | Corre `gastos.py assets/ejemplo.csv` y destaca la categoria con mayor porcentaje |
| "Pon esto en ropa, es un abrigo" | Corre con la columna `categoria` completa; no reclasifica lo que el usuario decidio |
| "Por que el taxi salio en otros?" | Explica la regla y muestra `--detalle` con la palabra clave que decidio |
| "Agrega 'panaderia Don Pero' a mis reglas" | Anade la palabra en `assets/categorias.json`, sin tocar codigo |
| "Esto tiene una columna que no entiendo" | Falla con codigo 1 y lista columnas requeridas y encontradas |

## Casos borde y manejo de errores

| Situacion | Que hace |
| --- | --- |
| Falta una columna requerida | No genera nada. Lista requeridas, opcionales y encontradas. Codigo 1 |
| Monto no numerico (`doce`) | Senala fila y valor. No genera nada. Codigo 1 |
| Fecha en formato desconocido (`ayer`) | Senala fila y formats aceptados. Codigo 1 |
| Categoria fuera de las 4 | Senala fila y las opciones validas. Codigo 1 |
| Varios errores a la vez | Acumula todos y los imprime juntos, hasta 12 |
| Archivo inexistente | Error de archivo, no de contenido. Codigo 2 |
| CSV vacio o solo cabeceras | Error explicito, no un resumen vacio silencioso |
| Compra sin palabra clave conocida | Va a `otros/sin_clasificar` y aparece en REVISAR. No es un error |
| Descripcion con acentos o signos | Se normaliza antes de buscar; `Farmacia` y `farmacia` funcionan igual |
| Monto con coma decimal | Funciona si el campo va entrecomillado: `"1.240,80"` |
| `gasolina` vs `gas` | No se confunde: la busqueda usa limites de palabra, no subcadenas |
| CSV exportado de Excel en Bolivia (`;`, `1.240,80`, `Descripción`) | Se procesa igual que uno con coma, sin configuración |
| Columna `Importe` en vez de `monto` | Se reconoce por sinonimo y se normaliza |
| Salida `.xlsx` sin `openpyxl` | Indica el comando de instalacion y termina con codigo 3; CSV no se afecta |

## Scripts ejecutables

- `scripts/gastos.py` — flujo completo. Uso:
  `python scripts/gastos.py <entrada.csv> [-o resumen.csv|resumen.xlsx] [-r assets/categorias.json] [-d]`
  La flag `-d/--detalle` imprime que palabra clave decido cada gasto y agrega la hoja `Detalle` a un XLSX.
  `-o` acepta `.csv` sin dependencias o `.xlsx` con `openpyxl>=3.1.0`.
  Códigos de salida: `0` ok, `1` entradas invalidas, `2` problema de archivo, `3` dependencia XLSX ausente.
- `scripts/demo.py` — demostracion de extremo a extremo. Corre 6 casos base y 1 caso de XLSX en una
  sola ejecucion. Cada caso reporta `PASA`, `FALLA` u `OMITIDO`; el de XLSX queda `OMITIDO` si
  `openpyxl` no esta instalado, y el demo sigue terminando con codigo `0`. Uso: `python scripts/demo.py`

## Assets

- `assets/requirements-xlsx.txt` — dependencia `openpyxl` necesaria solo para salidas `.xlsx`.
- `assets/categorias.json` — diccionario de palabras clave por categoria y subcategoria. Es el
  archivo que se edita para extender o corregir el comportamiento del clasificador.
- `assets/ejemplo.csv` — 15 gastos de ejemplo (incluye un caso ambiguo y uno sin regla) con
  separador de coma, que usa la demostracion.
- `assets/ejemplo-excel.csv` — los mismos 15 gastos tal como los exporta Excel en Bolivia:
  separador `;`, montos `1.240,80` y cabeceras con tilde. Sirve para comprobar que la skill
  entiende el formato real de entrada.

## Referencias

- `references/REGLAS-CLASIFICACION.md` — por que existe cada regla, como se desarman las
  ambiguedades y como agregar palabras clave.
- `references/FORMATO-ENTRADA.md` — columnas, formatos de fecha y monto, y la lista completa de
  errores con su causa.
