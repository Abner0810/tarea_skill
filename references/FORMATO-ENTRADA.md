# Formato de entrada

Contrato exacto que espera `scripts/gastos.py`. Se carga solo cuando una entrada es rechazada o
cuando hay que preparar un archivo nuevo.

## Columnas

| Columna | Obligatoria | Que es |
| --- | --- | --- |
| `fecha` | Si | Fecha del gasto. |
| `descripcion` | Si | Texto libre. De aqui se saca la categoria. |
| `monto` | Si | Cantidad en bolivianos. |
| `categoria` | No | `servicios`, `comida`, `ropa` u `otros`. Si se pone, la skill la respeta. |

## Separador de columnas

No hay que configurar nada. El script lee la primera linea y decide:

| La cabecera tiene | Usa como separador |
| --- | --- |
| mas `;` que `,` | `;` |
| cualquier otra cosa | `,` |

Esto es lo que permite leer sin cambios un CSV guardado desde Excel en Bolivia, que usa `;` como
separador de lista y `,` como separador decimal.

## Nombres de columna

Los nombres se comparan en minusculas y **sin acentos**, y los espacios, guiones bajos y guiones
se unifican a un solo espacio. Por eso estos cuatro son la misma columna:

```
descripcion   Descripción   DESCRIPCIÓN   Descripcion
```

Ademas se aceptan sinonimos, para no tener que renombrar a mano los exportes de bancos y apps:

| Columna canonica | Tambien acepta |
| --- | --- |
| `fecha` | `date` |
| `descripcion` | `concepto`, `detalle`, `observacion`, `desc` |
| `monto` | `importe`, `valor`, `total` |
| `categoria` | `categoria de gasto`, `rubro`, `tipo` |

Cualquier otro nombre se rechaza. La idea es no romper en silencio: una errata en la cabecera
(`montot`) haria que el archivo se procesara con datos incompletos, y es preferible un error
claro.

## Fechas aceptadas

| Formato | Ejemplo |
| --- | --- |
| `AAAA-MM-DD` | `2026-09-01` (recomendado) |
| `DD/MM/AAAA` | `01/09/2026` |
| `AAAA/MM/DD` | `2026/09/01` |

Cualquier otra cosa (`ayer`, `01-09-26`, `2026-13-01`) se rechaza indicando la fila.

## Montos aceptados

| Se escribe | Resultado | Nota |
| --- | --- | --- |
| `45.00` | 45.00 | Formato recomendado |
| `1.240,80` | 1240.80 | Con separador `,` **va entrecomillado**; con `;` va directo |
| `45,00` | 45.00 | Aceptado en los dos casos |
| `Bs 45` | 45.00 | Se ignora el prefijo |
| `0` | 0.00 | Valido |
| `-20` | rechazado | No se admiten montos negativos |
| `doce` | rechazado | Tiene que ser un numero |

La regla de las comillas es la trampa clasica de CSV: si el separador de columnas es la coma, un
monto con coma decimal rompe la fila. Por eso el ejemplo usa `"1.240,80"`.

Si el archivo esta guardado por Excel en Bolivia, suele venir con BOM. El script lo maneja
automáticamente, no hay que hacer nada.

## Ejemplo minimo valido

```csv
fecha,descripcion,monto
2026-09-01,Supermercado Maxi,240.80
2026-09-01,Factura de luz SETEX,185.50
2026-09-02,Taxi a la UCB,18
```

## Ejemplo con categoria manual

```csv
fecha,descripcion,monto,categoria
2026-09-08,Zapateria Nina,320.00,ropa
2026-09-09,Pago al plomero,400.00,otros
```

## Ejemplo exportado de Excel en Bolivia

```csv
Fecha;Descripción;Importe;Categoría
01/09/2026;Supermercado Maxi;1.240,80;
02/09/2026;Factura de luz SETEX;185,50;
```

Se procesa exactamente igual que el ejemplo minimo de arriba. Esta es la version de referencia en
`assets/ejemplo-excel.csv`.

## Errores y codigos de salida

| Codigo | Significado | Causas tipicas |
| --- | --- | --- |
| `0` | Se genero el resumen | Todo correcto |
| `1` | Entradas invalidas | Columna faltante, columna desconocida, monto no numerico, monto negativo, fecha invalida, categoria fuera de las 4, archivo vacio |
| `2` | Problema de archivo | El CSV no existe, el diccionario de reglas no existe o esta danado |
| `3` | Falta una dependencia | Se pidio una salida `.xlsx` y `openpyxl` no esta instalado |

El codigo `1` nunca genera una salida a medias: si hay un error, no hay salida. Asi no se toma una
decision sobre datos a medio leer.

## Salida Excel

La extension de `-o` decide el formato:

- `.csv`: salida tabular compatible con CSV y sin dependencias externas.
- `.xlsx`: libro Excel organizado en hojas `Resumen`, `Por subcategoria`, `Por categoria`, `Revisar`
  y `Detalle` cuando se usa `-d`.

Para usar `.xlsx`, instala `openpyxl` con:

```bash
python -m pip install -r assets/requirements-xlsx.txt
```

La entrada siempre es un CSV, incluido `assets/ejemplo-excel.csv`; ese archivo representa un export
de Excel con `;` y montos con coma decimal, no un libro `.xlsx`.

## Todos los mensajes de error

```
El archivo esta vacio o no tiene fila de cabecera.
Faltan columnas requeridas: <lista>.
Columnas encontradas: <lista>.
Requeridas: fecha, descripcion, monto.
Opcionales: categoria.
Formas aceptadas: <lista de sinonimos>.
Columnas no reconocidas: <lista>.
Fila <n>: la descripcion esta vacia.
Fila <n>: fecha invalida '<valor>' (usa AAAA-MM-DD o DD/MM/AAAA).
Fila <n>: monto invalido '<valor>' (debe ser un numero, por ejemplo 45.00 o "45,00").
Fila <n>: categoria invalida '<valor>' (opciones: servicios, comida, ropa, otros).
El archivo tiene cabeceras pero ningun gasto.
No se encontro el archivo de gastos: <ruta>
Para generar un archivo .xlsx instala openpyxl: python -m pip install openpyxl
```

Los errores se acumulan: un archivo con cinco filas malas muestra las cinco, no solo la primera.
Si superan los 12, se muestran los primeros 12 y se indica cuantos mas hay.

## Errores que NO son errores

Una compra que no se reconoce no falla el proceso. Va a `otros/sin_clasificar` y aparece en la
seccion `REVISAR` de la salida, que es el lugar para decidir si conviene agregarla al
diccionario. Ver `REGLAS-CLASIFICACION.md`.
