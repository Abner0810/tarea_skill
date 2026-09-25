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
CODIGO_DEPENDENCIA = 3
MAXIMO_ERRORES_MOSTRADOS = 12


class ErrorEntradas(Exception):
    def __init__(self, problemas):
        super().__init__("el archivo tiene entradas invalidas")
        self.problemas = problemas


class ErrorArchivo(Exception):
    pass


class ErrorDependencia(Exception):
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


def calcular_resumen_categoria(gastos):
    resumen = {}
    total = 0.0
    for gasto in gastos:
        categoria = gasto["categoria"]
        if categoria not in resumen:
            resumen[categoria] = {"n": 0, "total": 0.0}
        resumen[categoria]["n"] += 1
        resumen[categoria]["total"] += gasto["monto"]
        total += gasto["monto"]

    filas = [
        {
            "categoria": categoria,
            "n": datos["n"],
            "total": datos["total"],
            "porcentaje": (datos["total"] / total * 100) if total else 0.0,
        }
        for categoria, datos in resumen.items()
    ]
    filas.sort(key=lambda fila: (-fila["total"], fila["categoria"]))
    return filas, total


def seleccionar_revision(gastos):
    return [gasto for gasto in gastos if gasto["subcategoria"] == SIN_CLASIFICAR]


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


def escribir_xlsx(gastos, filas, total, salida, reglas, detalle):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as error:
        raise ErrorDependencia(
            "Para generar un archivo .xlsx instala openpyxl: "
            "python -m pip install openpyxl"
        ) from error

    ruta = Path(salida)
    if ruta.parent != Path("."):
        ruta.parent.mkdir(parents=True, exist_ok=True)

    moneda = reglas.get("moneda", "Bs")
    fechas = [gasto["fecha"] for gasto in gastos]
    color_principal = "1F4E78"
    color_encabezado = "5B9BD5"
    color_total = "D9EAF7"
    color_revisar = "FFF2CC"
    color_borde = "B4C7E7"
    borde = Border(
        left=Side(style="thin", color=color_borde),
        right=Side(style="thin", color=color_borde),
        top=Side(style="thin", color=color_borde),
        bottom=Side(style="thin", color=color_borde),
    )

    libro = Workbook()
    libro.remove(libro.active)
    libro.properties.title = "Control de gastos"
    libro.properties.subject = "Resumen de gastos clasificados"

    def texto(hoja, fila, columna, valor):
        celda = hoja.cell(fila, columna)
        celda.value = "" if valor is None else str(valor)
        celda.data_type = "s"
        return celda

    def titulo(hoja, nombre, columnas):
        hoja.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columnas)
        celda = hoja.cell(1, 1)
        celda.value = nombre
        celda.font = Font(size=16, bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor=color_principal)
        celda.alignment = Alignment(horizontal="left", vertical="center")
        hoja.row_dimensions[1].height = 28

    def encabezados(hoja, fila, valores):
        for columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(fila, columna, valor)
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor=color_encabezado)
            celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            celda.border = borde
        hoja.row_dimensions[fila].height = 28

    def ajustar(hoja, anchos):
        for indice, ancho in enumerate(anchos, start=1):
            hoja.column_dimensions[get_column_letter(indice)].width = ancho
        hoja.sheet_view.showGridLines = False
        hoja.sheet_view.zoomScale = 90

    def preparar_tabla(hoja, fila_encabezado, columnas, ultima_fila, anchos):
        ajustar(hoja, anchos)
        hoja.freeze_panes = f"A{fila_encabezado + 1}"
        if ultima_fila >= fila_encabezado:
            hoja.auto_filter.ref = (
                f"A{fila_encabezado}:{get_column_letter(columnas)}{ultima_fila}"
            )

    def marcar_total(hoja, fila, columnas):
        for columna in range(1, columnas + 1):
            celda = hoja.cell(fila, columna)
            celda.font = Font(bold=True, color=color_principal)
            celda.fill = PatternFill("solid", fgColor=color_total)
            celda.border = Border(top=Side(style="double", color=color_principal))

    def seccion(hoja, fila, nombre, columnas):
        hoja.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=columnas)
        celda = hoja.cell(fila, 1)
        celda.value = nombre
        celda.font = Font(bold=True, size=12, color=color_principal)

    def etiqueta_categoria(categoria):
        definicion = reglas.get("categorias", {}).get(categoria, {})
        return definicion.get("etiqueta", categoria)

    def origen(gasto):
        return "Clasificado automaticamente" if gasto["automatica"] else "Categoria manual"

    def aplicar_formato_monto(celda):
        celda.number_format = f'#,##0.00 "{moneda}"'

    def aplicar_formato_porcentaje(celda):
        celda.number_format = "0.0%"

    def aplicar_formato_fecha(celda):
        celda.number_format = "yyyy-mm-dd"

    hoja = libro.create_sheet("Resumen")
    titulo(hoja, "CONTROL DE GASTOS", 4)
    datos_resumen = [
        (3, "Periodo", f"{min(fechas)} a {max(fechas)}"),
        (4, "Gastos", len(gastos)),
        (5, f"Total ({moneda})", total),
    ]
    for fila, etiqueta, valor in datos_resumen:
        texto(hoja, fila, 1, etiqueta).font = Font(bold=True, color=color_principal)
        celda = hoja.cell(fila, 2, valor)
        if fila == 5:
            aplicar_formato_monto(celda)
    seccion(hoja, 7, "RESUMEN POR CATEGORIA", 4)
    encabezados(hoja, 8, ["CATEGORIA", "N GASTOS", f"TOTAL ({moneda})", "% DEL TOTAL"])
    filas_categoria, _ = calcular_resumen_categoria(gastos)
    for indice, fila in enumerate(filas_categoria, start=9):
        texto(hoja, indice, 1, etiqueta_categoria(fila["categoria"]))
        hoja.cell(indice, 2, fila["n"])
        celda = hoja.cell(indice, 3, fila["total"])
        aplicar_formato_monto(celda)
        celda = hoja.cell(indice, 4, fila["porcentaje"] / 100)
        aplicar_formato_porcentaje(celda)
    fila_total = 9 + len(filas_categoria)
    texto(hoja, fila_total, 1, "TOTAL")
    hoja.cell(fila_total, 2, len(gastos))
    celda = hoja.cell(fila_total, 3, total)
    aplicar_formato_monto(celda)
    celda = hoja.cell(fila_total, 4, 1.0)
    aplicar_formato_porcentaje(celda)
    marcar_total(hoja, fila_total, 4)
    ajustar(hoja, [24, 14, 20, 16])
    hoja.freeze_panes = "A9"
    hoja.print_area = f"A1:D{fila_total}"

    hoja = libro.create_sheet("Por subcategoria")
    titulo(hoja, "POR SUBCATEGORIA", 5)
    encabezados(
        hoja,
        3,
        ["CATEGORIA", "SUBCATEGORIA", "N GASTOS", f"TOTAL ({moneda})", "% DEL TOTAL"],
    )
    for indice, fila in enumerate(filas, start=4):
        texto(hoja, indice, 1, etiqueta_categoria(fila["categoria"]))
        texto(hoja, indice, 2, fila["subcategoria"])
        hoja.cell(indice, 3, fila["n"])
        celda = hoja.cell(indice, 4, fila["total"])
        aplicar_formato_monto(celda)
        celda = hoja.cell(indice, 5, fila["porcentaje"] / 100)
        aplicar_formato_porcentaje(celda)
    fila_total = 4 + len(filas)
    texto(hoja, fila_total, 1, "TOTAL")
    texto(hoja, fila_total, 2, "")
    hoja.cell(fila_total, 3, len(gastos))
    celda = hoja.cell(fila_total, 4, total)
    aplicar_formato_monto(celda)
    celda = hoja.cell(fila_total, 5, 1.0)
    aplicar_formato_porcentaje(celda)
    marcar_total(hoja, fila_total, 5)
    preparar_tabla(hoja, 3, 5, fila_total, [20, 22, 14, 20, 16])

    hoja = libro.create_sheet("Por categoria")
    titulo(hoja, "POR CATEGORIA", 4)
    encabezados(hoja, 3, ["CATEGORIA", "N GASTOS", f"TOTAL ({moneda})", "% DEL TOTAL"])
    for indice, fila in enumerate(filas_categoria, start=4):
        texto(hoja, indice, 1, etiqueta_categoria(fila["categoria"]))
        hoja.cell(indice, 2, fila["n"])
        celda = hoja.cell(indice, 3, fila["total"])
        aplicar_formato_monto(celda)
        celda = hoja.cell(indice, 4, fila["porcentaje"] / 100)
        aplicar_formato_porcentaje(celda)
    fila_total = 4 + len(filas_categoria)
    texto(hoja, fila_total, 1, "TOTAL")
    hoja.cell(fila_total, 2, len(gastos))
    celda = hoja.cell(fila_total, 3, total)
    aplicar_formato_monto(celda)
    celda = hoja.cell(fila_total, 4, 1.0)
    aplicar_formato_porcentaje(celda)
    marcar_total(hoja, fila_total, 4)
    preparar_tabla(hoja, 3, 4, fila_total, [24, 14, 20, 16])

    hoja = libro.create_sheet("Revisar")
    titulo(hoja, "GASTOS PARA REVISAR", 7)
    encabezados(
        hoja,
        3,
        ["FILA", "FECHA", "DESCRIPCION", f"MONTO ({moneda})", "CATEGORIA", "SUBCATEGORIA", "ORIGEN"],
    )
    revisar = seleccionar_revision(gastos)
    if revisar:
        for indice, gasto in enumerate(revisar, start=4):
            hoja.cell(indice, 1, gasto["fila"])
            celda = hoja.cell(indice, 2, gasto["fecha"])
            aplicar_formato_fecha(celda)
            texto(hoja, indice, 3, gasto["descripcion"])
            celda = hoja.cell(indice, 4, gasto["monto"])
            aplicar_formato_monto(celda)
            texto(hoja, indice, 5, etiqueta_categoria(gasto["categoria"]))
            texto(hoja, indice, 6, gasto["subcategoria"])
            texto(hoja, indice, 7, origen(gasto))
            for columna in range(1, 8):
                hoja.cell(indice, columna).fill = PatternFill("solid", fgColor=color_revisar)
        ultima_fila = 3 + len(revisar)
        preparar_tabla(hoja, 3, 7, ultima_fila, [10, 14, 32, 20, 18, 20, 26])
    else:
        texto(hoja, 4, 1, "No hay gastos que requieran revision.")
        ajustar(hoja, [10, 14, 32, 20, 18, 20, 26])

    if detalle:
        hoja = libro.create_sheet("Detalle")
        titulo(hoja, "DETALLE DE CLASIFICACION", 8)
        encabezados(
            hoja,
            3,
            [
                "FILA",
                "FECHA",
                "DESCRIPCION",
                f"MONTO ({moneda})",
                "CATEGORIA",
                "SUBCATEGORIA",
                "PALABRA CLAVE",
                "ORIGEN",
            ],
        )
        for indice, gasto in enumerate(gastos, start=4):
            hoja.cell(indice, 1, gasto["fila"])
            celda = hoja.cell(indice, 2, gasto["fecha"])
            aplicar_formato_fecha(celda)
            texto(hoja, indice, 3, gasto["descripcion"])
            celda = hoja.cell(indice, 4, gasto["monto"])
            aplicar_formato_monto(celda)
            texto(hoja, indice, 5, etiqueta_categoria(gasto["categoria"]))
            texto(hoja, indice, 6, gasto["subcategoria"])
            texto(hoja, indice, 7, gasto["palabra_clave"] or "-")
            texto(hoja, indice, 8, origen(gasto))
        preparar_tabla(hoja, 3, 8, 3 + len(gastos), [10, 14, 32, 20, 18, 20, 22, 26])

    libro.active = 0
    libro.save(ruta)


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

    filas_categoria, _ = calcular_resumen_categoria(gastos)
    print()
    print("POR CATEGORIA (tus 4 cajones)")
    for fila in filas_categoria:
        porcentaje = f"{fila['porcentaje']:>5,.1f}%"
        print(
            f"  {fila['categoria']:<12}{moneda} {fila['total']:>10,.2f}  "
            f"({porcentaje})"
        )

    revisar = seleccionar_revision(gastos)
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


def es_salida_xlsx(salida):
    return Path(salida).suffix.lower() == ".xlsx"


def ejecutar(entrada, salida, ruta_reglas, detalle):
    if not Path(entrada).exists():
        raise ErrorArchivo(f"No se encontro el archivo de gastos: {entrada}")

    reglas = cargar_reglas(ruta_reglas)
    gastos = cargar_gastos(entrada, reglas)
    filas, total = calcular_resumen(gastos)
    if es_salida_xlsx(salida):
        escribir_xlsx(gastos, filas, total, salida, reglas, detalle)
    else:
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
        "-o",
        "--salida",
        default="resumen.csv",
        help="Archivo de salida: .csv (CSV) o .xlsx (Excel; requiere openpyxl).",
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
    except ErrorDependencia as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return CODIGO_DEPENDENCIA
    return CODIGO_OK


if __name__ == "__main__":
    sys.exit(main())
