import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CAMPOS_REQUERIDOS = ["fecha", "descripcion", "monto"]
CAMPOS_OPCIONALES = ["categoria"]
CATEGORIAS_PERMITIDAS = ["servicios", "comida", "ropa", "otros"]
FORMATOS_FECHA = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]
SINONIMOS = {
    "fecha": ["fecha", "date"],
    "descripcion": ["descripcion", "concepto", "detalle", "observacion", "desc"],
    "monto": ["monto", "importe", "valor", "total"],
    "categoria": ["categoria", "categoria de gasto", "rubro", "tipo"],
}
SIN_CLASIFICAR = "sin_clasificar"
RAIZ_SKILL = Path(__file__).resolve().parent.parent
RUTA_REGLAS_POR_DEFECTO = RAIZ_SKILL / "assets" / "categorias.json"
CODIGO_OK = 0
CODIGO_ENTRADAS = 1
CODIGO_ARCHIVO = 2
MAXIMO_ERRORES_MOSTRADOS = 12


class ErrorEntradas(Exception):
    def __init__(self, problemas):
        super().__init__("el archivo tiene entradas invalidas")
        self.problemas = problemas


class ErrorArchivo(Exception):
    pass


def normalizar(texto):
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", sin_acentos)


def cargar_reglas(ruta):
    try:
        with open(ruta, encoding="utf-8") as archivo:
            reglas = json.load(archivo)
    except FileNotFoundError:
        raise ErrorArchivo(f"No se encontro el diccionario de reglas: {ruta}")
    except json.JSONDecodeError as error:
        raise ErrorArchivo(f"El diccionario de reglas esta danado ({ruta}): {error}")

    categorias = reglas.get("categorias", {})
    faltantes = [nombre for nombre in CATEGORIAS_PERMITIDAS if nombre not in categorias]
    if faltantes:
        raise ErrorArchivo(
            f"El diccionario de reglas no define estas categorias: {', '.join(faltantes)}"
        )
    return reglas


def indice_palabras_clave(reglas):
    indice = []
    for categoria, definicion in reglas["categorias"].items():
        for subcategoria, palabras in definicion.get("subcategorias", {}).items():
            for palabra in palabras:
                indice.append((palabra, categoria, subcategoria))
    return indice


def clasificar(descripcion, indice, categoria_forzada=None):
    texto = normalizar(descripcion)
    mejor = None
    for palabra, categoria, subcategoria in indice:
        if categoria_forzada and categoria != categoria_forzada:
            continue
        patron = r"(?<![a-z0-9])" + re.escape(normalizar(palabra)) + r"(?![a-z0-9])"
        if not re.search(patron, texto):
            continue
        candidata = (categoria, subcategoria, palabra)
        if mejor is None:
            mejor = candidata
            continue
        if (len(palabra), palabra) > (len(mejor[2]), mejor[2]):
            mejor = candidata
    if mejor is None:
        return (categoria_forzada or "otros"), SIN_CLASIFICAR, None
    return mejor


def parsear_fecha(valor):
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(valor.strip(), formato).date()
        except ValueError:
            continue
    return None


def parsear_monto(valor):
    limpio = valor.strip().lower().replace("bs", "").strip()
    if not limpio:
        return None
    if "," in limpio and "." in limpio:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    else:
        limpio = limpio.replace(",", ".")
    try:
        monto = float(limpio)
    except ValueError:
        return None
    return monto if monto >= 0 else None


def normalizar_cabecera(nombre):
    return " ".join(normalizar(nombre).split())


def detectar_separador(archivo):
    with open(archivo, encoding="utf-8-sig") as manejado:
        primera = manejado.readline()
    return ";" if primera.count(";") > primera.count(",") else ","


def leer_encabezado(archivo, separador):
    with open(archivo, newline="", encoding="utf-8-sig") as manejado:
        lector = csv.reader(manejado, delimiter=separador)
        for fila in lector:
            if fila and any(campo.strip() for campo in fila):
                return [normalizar_cabecera(campo) for campo in fila]
    return []


def resolver_columnas(encabezado):
    columnas = {}
    for canonico, alias in SINONIMOS.items():
        for nombre in alias:
            if nombre in encabezado:
                columnas[canonico] = nombre
                break
    return columnas


def validar_cabecera(encabezado, columnas):
    if not encabezado:
        raise ErrorEntradas(["El archivo esta vacio o no tiene fila de cabecera."])

    faltantes = [campo for campo in CAMPOS_REQUERIDOS if campo not in columnas]
    if faltantes:
        aceptadas = sorted({alias for alias in SINONIMOS.values() for alias in alias})
        raise ErrorEntradas(
            [
                f"Faltan columnas requeridas: {', '.join(faltantes)}.",
                f"Columnas encontradas: {', '.join(encabezado)}.",
                f"Requeridas: {', '.join(CAMPOS_REQUERIDOS)}.",
                f"Opcionales: {', '.join(CAMPOS_OPCIONALES)}.",
                f"Formas aceptadas: {', '.join(aceptadas)}.",
            ]
        )

    reconocidas = set(columnas.values())
    desconocidas = [nombre for nombre in encabezado if nombre not in reconocidas]
    if desconocidas:
        raise ErrorEntradas(
            [
                f"Columnas no reconocidas: {', '.join(desconocidas)}.",
                "Revisa el nombre exacto de las columnas en references/FORMATO-ENTRADA.md.",
            ]
        )


def cargar_gastos(archivo, reglas):
    separador = detectar_separador(archivo)
    encabezado = leer_encabezado(archivo, separador)
    columnas = resolver_columnas(encabezado)
    validar_cabecera(encabezado, columnas)

    indice = indice_palabras_clave(reglas)
    posicion = {
        canonico: encabezado.index(nombre) for canonico, nombre in columnas.items()
    }
    problemas = []
    gastos = []

    with open(archivo, newline="", encoding="utf-8-sig") as manejado:
        lector = csv.reader(manejado, delimiter=separador)
        next(lector, None)
        for numero, fila in enumerate(lector, start=2):
            if not fila or not any(campo.strip() for campo in fila):
                continue

            def valor(campo):
                indice_campo = posicion.get(campo)
                if indice_campo is None or indice_campo >= len(fila):
                    return ""
                return fila[indice_campo].strip()

            descripcion = valor("descripcion")
            if not descripcion:
                problemas.append(f"Fila {numero}: la descripcion esta vacia.")
                continue

            fecha = parsear_fecha(valor("fecha"))
            if fecha is None:
                problemas.append(
                    f"Fila {numero}: fecha invalida '{valor('fecha')}' "
                    f"(usa AAAA-MM-DD o DD/MM/AAAA)."
                )

            monto = parsear_monto(valor("monto"))
            if monto is None:
                problemas.append(
                    f"Fila {numero}: monto invalido '{valor('monto')}' "
                    f"(debe ser un numero, por ejemplo 45.00 o \"45,00\")."
                )

            categoria = valor("categoria").lower()
            categoria_valida = categoria in CATEGORIAS_PERMITIDAS
            if categoria and not categoria_valida:
                problemas.append(
                    f"Fila {numero}: categoria invalida '{categoria}' "
                    f"(opciones: {', '.join(CATEGORIAS_PERMITIDAS)})."
                )

            if fecha is None or monto is None or (categoria and not categoria_valida):
                continue

            resuelta, subcategoria, palabra = clasificar(
                descripcion, indice, categoria or None
            )
            gastos.append(
                {
                    "fila": numero,
                    "fecha": fecha,
                    "descripcion": descripcion,
                    "monto": monto,
                    "categoria": resuelta,
                    "subcategoria": subcategoria,
                    "palabra_clave": palabra,
                    "automatica": not bool(categoria),
                }
            )

    if problemas:
        raise ErrorEntradas(problemas)
    if not gastos:
        raise ErrorEntradas(["El archivo tiene cabeceras pero ningun gasto."])
    return gastos


def calcular_resumen(gastos):
    resumen = {}
    total = 0.0
    for gasto in gastos:
        clave = (gasto["categoria"], gasto["subcategoria"])
        if clave not in resumen:
            resumen[clave] = {"n": 0, "total": 0.0}
        resumen[clave]["n"] += 1
        resumen[clave]["total"] += gasto["monto"]
        total += gasto["monto"]

    filas = [
        {
            "categoria": categoria,
            "subcategoria": subcategoria,
            "n": datos["n"],
            "total": datos["total"],
            "porcentaje": (datos["total"] / total * 100) if total else 0.0,
        }
        for (categoria, subcategoria), datos in resumen.items()
    ]
    filas.sort(key=lambda fila: (-fila["total"], fila["categoria"]))
    return filas, total


def escribir_csv(filas, total, salida):
    ruta = Path(salida)
    if ruta.parent != Path("."):
        ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(
            ["categoria", "subcategoria", "n_gastos", "total_bs", "porcentaje"]
        )
        for fila in filas:
            escritor.writerow(
                [
                    fila["categoria"],
                    fila["subcategoria"],
                    fila["n"],
                    f"{fila['total']:.2f}",
                    f"{fila['porcentaje']:.2f}",
                ]
            )
        escritor.writerow(
            ["TOTAL", "", sum(fila["n"] for fila in filas), f"{total:.2f}", "100.00"]
        )


def imprimir_consola(gastos, filas, total, reglas, salida, detalle):
    moneda = reglas.get("moneda", "Bs")
    fechas = [gasto["fecha"] for gasto in gastos]
    ancho = 64

    print()
    print("CONTROL DE GASTOS".ljust(ancho))
    print("=" * ancho)
    print(f"Periodo : {min(fechas)} a {max(fechas)}")
    print(f"Gastos  : {len(gastos)}")
    print(f"Total   : {moneda} {total:,.2f}")
    print()
    print(f"{'CATEGORIA':<13}{'SUBCATEGORIA':<17}{'N':>3}{'TOTAL':>14}{'%':>8}")
    print("-" * ancho)
    for fila in filas:
        print(
            f"{fila['categoria']:<13}{fila['subcategoria']:<17}"
            f"{fila['n']:>3}{fila['total']:>14,.2f}{fila['porcentaje']:>7,.1f}%"
        )
    print("-" * ancho)

    por_categoria = {}
    for fila in filas:
        por_categoria[fila["categoria"]] = por_categoria.get(fila["categoria"], 0.0) + fila["total"]
    print()
    print("POR CATEGORIA (tus 4 cajones)")
    for categoria, monto in sorted(por_categoria.items(), key=lambda par: -par[1]):
        print(f"  {categoria:<12}{moneda} {monto:>10,.2f}  ({monto / total * 100:>5,.1f}%)")

    revisar = [gasto for gasto in gastos if gasto["subcategoria"] == SIN_CLASIFICAR]
    if revisar:
        print()
        print(f"REVISAR: {len(revisar)} gasto(s) sin regla explicita (quedaron en otros)")
        for gasto in revisar:
            origen = "categoria manual" if not gasto["automatica"] else "clasificado solo"
            print(
                f"  fila {gasto['fila']:>3} | {gasto['descripcion']:<30}"
                f"{moneda} {gasto['monto']:>9,.2f}  ({origen})"
            )
        print("  Para que dejen de aparecer aca, agrega la palabra en assets/categorias.json.")

    if detalle:
        print()
        print("DETALLE DE CLASIFICACION (que palabra decidio cada gasto)")
        for gasto in gastos:
            palabra = gasto["palabra_clave"] or "-"
            print(
                f"  fila {gasto['fila']:>3} | {gasto['descripcion']:<30}"
                f"-> {gasto['categoria']}/{gasto['subcategoria']}  (por '{palabra}')"
            )

    print()
    print(f"Resumen escrito en: {salida}")
    print()


def ejecutar(entrada, salida, ruta_reglas, detalle):
    if not Path(entrada).exists():
        raise ErrorArchivo(f"No se encontro el archivo de gastos: {entrada}")

    reglas = cargar_reglas(ruta_reglas)
    gastos = cargar_gastos(entrada, reglas)
    filas, total = calcular_resumen(gastos)
    escribir_csv(filas, total, salida)
    imprimir_consola(gastos, filas, total, reglas, salida, detalle)
    return len(gastos), total


def main():
    analizador = argparse.ArgumentParser(
        prog="gastos.py",
        description="Clasifica gastos en servicios/comida/ropa/otros y genera un resumen.",
    )
    analizador.add_argument("entrada", help="Archivo CSV de gastos.")
    analizador.add_argument(
        "-o", "--salida", default="resumen.csv", help="CSV de salida (resumen.csv)."
    )
    analizador.add_argument(
        "-r",
        "--reglas",
        default=str(RUTA_REGLAS_POR_DEFECTO),
        help="Diccionario de categorias (assets/categorias.json).",
    )
    analizador.add_argument(
        "-d",
        "--detalle",
        action="store_true",
        help="Muestra que palabra clave decidio cada gasto.",
    )
    argumentos = analizador.parse_args()

    try:
        ejecutar(
            argumentos.entrada, argumentos.salida, argumentos.reglas, argumentos.detalle
        )
    except ErrorEntradas as error:
        print("ERROR: no se pudo procesar el archivo.", file=sys.stderr)
        for problema in error.problemas[:MAXIMO_ERRORES_MOSTRADOS]:
            print(f"  - {problema}", file=sys.stderr)
        restantes = len(error.problemas) - MAXIMO_ERRORES_MOSTRADOS
        if restantes > 0:
            print(f"  - ... y {restantes} problema(s) mas.", file=sys.stderr)
        print("Consulta references/FORMATO-ENTRADA.md", file=sys.stderr)
        return CODIGO_ENTRADAS
    except ErrorArchivo as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return CODIGO_ARCHIVO
    return CODIGO_OK


if __name__ == "__main__":
    sys.exit(main())
