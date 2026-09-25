# control-gastos

Skill que toma un CSV de compras, clasifica cada gasto en **servicios**, **comida**, **ropa** u
**otros**, y devuelve un resumen con totales, porcentajes y subcategorias.

La clasificacion es determinista: sin IA, sin API, sin claves y sin internet. La misma entrada
produce siempre el mismo resultado, y el usuario puede ver que palabra clave decido cada gasto.

## Requisitos

- Python 3.10 o superior.
- Nada mas. Cero dependencias, no hace falta `pip install`.

Comprobar version: `python --version`

## Estructura

```
skill-control-gastos/
├── SKILL.md                              # descripcion y reglas de la skill
├── README.md                             # este archivo
├── scripts/
│   ├── gastos.py                         # flujo completo: valida, clasifica, resume
│   └── demo.py                           # 1 caso exitoso + 4 casos de error
├── assets/
│   ├── categorias.json                   # diccionario de palabras clave (se edita a mano)
│   ├── ejemplo.csv                       # 15 gastos, separador de coma
│   └── ejemplo-excel.csv                 # los mismos 15, como los exporta Excel en Bolivia
└── references/
    ├── REGLAS-CLASIFICACION.md           # por que clasifica asi y como extenderlo
    └── FORMATO-ENTRADA.md                # columnas, formatos y todos los errores
```

## Instalacion

La skill se instala copiando la carpeta completa a una ruta que opencode ya escanea. No hace falta
tocar ninguna configuracion.

**Windows:**

```cmd
mkdir "%USERPROFILE%\.agents\skills"
xcopy /E /I /Y control-gastos "%USERPROFILE%\.agents\skills\control-gastos"
```

**Linux o macOS:**

```bash
mkdir -p ~/.agents/skills
cp -R control-gastos ~/.agents/skills/control-gastos
```

Despues hay que **reiniciar opencode**: las skills se cargan al arrancar y no se recargan en
caliente.

### Sincronizar los cambios

Si se desarrollo en la carpeta de trabajo, hay que volver a copiar antes de probar o presentar:

```cmd
xcopy /E /I /Y control-gastos "%USERPROFILE%\.agents\skills\control-gastos"
```

### Verificar la instalacion

```cmd
python "%USERPROFILE%\.agents\skills\control-gastos\scripts\demo.py"
```

Y desde el chat de opencode, con un mensaje normal: `usá la skill control-gastos y clasificame
C:\ruta\de\mis-gastos.csv`

## Como usarla

### 1. Caso exitoso

```bash
python scripts/gastos.py assets/ejemplo.csv
```

Salida en consola:

```
CONTROL DE GASTOS
================================================================
Periodo : 2026-09-01 a 2026-09-13
Gastos  : 15
Total   : Bs 3,162.80

CATEGORIA    SUBCATEGORIA       N         TOTAL       %
----------------------------------------------------------------
comida       supermercado       1      1,240.80   39.2%
otros        hogar              1        400.00   12.6%
ropa         calzado            1        320.00   10.1%
...
```

Y genera `resumen.csv`:

```csv
categoria,subcategoria,n_gastos,total_bs,porcentaje
comida,supermercado,1,1240.80,39.23
otros,hogar,1,400.00,12.65
...
TOTAL,,15,3162.80,100.00
```

### 2. Ver que palabra decidio cada gasto

```bash
python scripts/gastos.py assets/ejemplo.csv -d
```

Agrega una seccion `DETALLE DE CLASIFICACION` al final:

```
fila   4 | Supermercado Maxi             -> comida/supermercado  (por 'supermercado')
fila  12 | Pago al plomero               -> otros/hogar  (por 'plomero')
fila  16 | Regalo para mi mama           -> otros/sin_clasificar  (por '-')
```

### 3. Con tus propios gastos

Copiar `assets/ejemplo.csv`, poner tus filas, y:

```bash
python scripts/gastos.py mis-gastos.csv -o mi-resumen.csv
```

### 4. Con un archivo exportado de Excel

```bash
python scripts/gastos.py assets/ejemplo-excel.csv
```

Funciona sin configurar nada. Excel en Bolivia exporta con `;` como separador, `,` como decimal y
cabeceras con tilde (`Descripción`, `Importe`); la skill detecta el formato y tambien acepta
`Importe` como sinonimo de `monto` y `Concepto` como sinonimo de `descripcion`.

### 5. Entrada invalida

```bash
python scripts/gastos.py datos_malos.csv
```

```
ERROR: no se pudo procesar el archivo.
  - Fila 2: monto invalido 'doce' (debe ser un numero, por ejemplo 45.00 o "45,00").
  - Fila 3: fecha invalida 'ayer' (usa AAAA-MM-DD o DD/MM/AAAA).
Consulta references/FORMATO-ENTRADA.md
```

No genera `resumen.csv` a medias. Sale con codigo `1`.

## Opciones

| Opcion | Por defecto | Para que sirve |
| --- | --- | --- |
| `-o, --salida` | `resumen.csv` | Cambiar el nombre o la carpeta del CSV de salida |
| `-r, --reglas` | `assets/categorias.json` | Usar otro diccionario de categorias |
| `-d, --detalle` | apagado | Mostrar que palabra clave decidio cada gasto |

## Demostracion

```bash
python scripts/demo.py
```

Corre 6 casos de punta a punta y termina con `6/6 casos pasan`:

| Caso | Que prueba |
| --- | --- |
| 1 | Clasifica los 15 gastos de ejemplo y el total da Bs 3,162.80 |
| 2 | Rechaza un CSV sin la columna `monto` |
| 3 | Senala la fila con monto no numerico |
| 4 | Acumula dos errores distintos en una sola corrida |
| 5 | Distingue archivo inexistente de contenido invalido |
| 6 | Lee el formato real de Excel en Bolivia (`;`, `1.240,80`, tildes) y da el mismo total |

## Como extenderla

Para agregar una palabra clave no se toca Python. Se edita `assets/categorias.json`:

```json
"salud": ["farmacia", "medico", "doctor", "dentista", "analisis", "hospital", "medicamento"]
```

Para agregar una subcategoria nueva, se agrega una clave dentro de su categoria. El script las
descubre sola, no hay lista que actualizar en el codigo.

## Requisitos del CSV de entrada

Encabezado con `fecha`, `descripcion`, `monto`, y opcionalmente `categoria`. Detalle completo,
ejemplos y la lista de errores en `references/FORMATO-ENTRADA.md`.

```csv
fecha,descripcion,monto
2026-09-01,Supermercado Maxi,240.80
2026-09-01,Factura de luz SETEX,185.50
2026-09-02,Taxi a la UCB,18
```

## Decisiones de diseno

**Por que Python y no Bash.** Los ejemplos de la clase usan scripts `.sh`, que en Windows no
corren sin WSL ni Git Bash. Python viene instalado en la mayoria de las maquinas y es el mismo
en los tres sistemas, asi que la demo funciona en la presentacion sin condiciones.

**Por que un diccionario y no un modelo.** Un modelo puede clasificar "Regalo para mi mama" en
`ropa` con un 60% de confianza y nadie puede explicar por que. Con reglas, cada decision tiene una
palabra clave visible, y lo que no se reconoce cae en `otros` con aviso, no con una suposicion.

**Por que `otros` es una categoria y no un error.** Es la red de seguridad. Permite que la skill
acepte cualquier compra sin romperse, y a la vez mide cuanto cae ahi: la seccion `REVISAR` dice
cuanto dinero se esta classifying sin regla, que es justamente el trabajo de mejorar el
diccionario.

**Por que acumula errores.** Reportar el primer problema y frenar obliga a corregir y volver a
correr cinco veces. Reportarlos todos de una vez convierte cinco correcciones en una.

**Por que rechaza columnas desconocidas.** Una errata en la cabecera (`montot`) haria que el
archivo se procesara con una columna faltante y datos incompletos. Es mejor un error claro. Las
columnas con sinonimo conocido (`importe`, `concepto`) si se aceptan, para no obligar a renombrar
a mano los exportes de bancos.

**Por que detecta el separador solo.** Un CSV guardado desde Excel en Bolivia usa `;` y `,` como
decimal, exactamente al reves que el ejemplo de la clase. Obligar al usuario a convertir el
archivo antes de usarlo seria poner el trabajo de adaptacion de formato de parte de quien
presenta. Detectar el formato real es lo que hace que la skill funcione con datos de verdad.
