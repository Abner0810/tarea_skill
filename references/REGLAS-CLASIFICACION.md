# Reglas de clasificacion

Este documento explica por que el clasificador decide lo que decide. Se carga solo cuando hace
falta entender o corregir una clasificacion.

## Las cuatro categorias

| Categoria | Criterio |
| --- | --- |
| `servicios` | Un servicio recurrente del hogar: se paga todos los meses y el beneficiario es la vivienda o la conexion, no un consumo puntual. |
| `comida` | Alimento o bebida. Incluye lo que se compra para comer en casa y lo que se come afuera. |
| `ropa` | Algo que se viste o que se lleva puesto: prendas, calzado, accesorios. |
| `otros` | Todo lo demas. Es una categoria real, no un error. |

## Principio de desempate

Cuando varias palabras clave coinciden en una misma descripcion, **gana la mas larga**.

Ejemplo: `Supermercado Maxi` coincide con `supermercado` (11 letras) y con `maxi` (4 letras).
Gana `supermercado`. En el diccionario actual las dos palabras apuntan al mismo lugar, asi que el
resultado no cambia; la diferencia se nota cuando una palabra generica y otra especifica apuntan a
categorias distintas, y en ese caso manda la especifica.

Si dos coincidencias tienen el mismo largo, gana la primera en el orden del diccionario, que es
fijo. Por eso el resultado es siempre el mismo.

## Por que limites de palabra y no subcadenas

La busqueda exige que la palabra clave este rodeada de limites de palabra. Sin esto, `gas`
dentro de `gasolina` haria que cada gasto de bencina terminara en `servicios/gas`. Los limites
evitan tres tipos de falsos positivos:

| Palabra clave | Sin limites | Con limites |
| --- | --- | --- |
| `gas` | `gasolina`, `gasolinera` | `garrafa de gas` |
| `u` | `UCB`, `Ubuntu` | `u azul` |
| `pan` | `pantal`, `pantalones` | `pan de yuca` |

## Normalizacion

Antes de buscar, cada descripcion se pasa por esta cadena:

1. Todo a minusculas.
2. Se separan los acentos: `Farmacia CRUZEÑO` -> `farmacia cruzero`.
3. Los signos que no sean letras ni numeros se convierten en espacio.

Por eso el usuario puede escribir como quiera y el diccionario no necesita variantes.

## Ambiguedades resueltas

`servicios` en Bolivia tiene dos significados. La skill toma el primero (servicio recurrente del
hogar) y descarta el segundo (contratar a alguien).

| Descripcion | Resultado | Por que |
| --- | --- | --- |
| `pago internet Entel` | `servicios/telefonia` | Servicio recurrente. |
| `pago al plomero` | `otros/hogar` | Trabajo puntual, no se paga todos los meses. |
| `compra de gas LP` | `servicios/gas` | Servicio recurrente del hogar. |
| `gasolina 50` | `otros/transporte` | Combustible, no servicio. Los limites de palabra separan los casos. |
| `taxi a la UCB` | `otros/transporte` | `taxi` gana. `u` sola no matchea `UCB`. |
| `Regalo para mi mama` | `otros/sin_clasificar` | Ninguna palabra conocida. Aparece en REVISAR. |

## La categoria manual manda

Si el CSV trae la columna `categoria` con uno de los cuatro valores, la skill **no** busca
palabras clave para decidir la categoria. Respeta la decision del usuario. Solo usa el
diccionario para encontrar la subcategoria dentro de la categoria elegida.

Por ejemplo, si pones `Zapateria Nina,320,ropa`, el resultado es `ropa/calzado` porque `zapateria`
esta dentro de `ropa`. Si pones `Zapateria Nina,320,comida`, el resultado es `comida/sin_clasificar`
y no se corrige: la skill no reinterpreta al usuario.

## Como agregar o corregir una palabra

1. Abrir `assets/categorias.json`.
2. En la subcategoria correspondiente, agregar la palabra al final de la lista.
3. Probar: `python scripts/demo.py`.

Ejemplo, para que `farmacia` deje de aparecer en REVISAR con la palabra `salvavidas`:

```json
"salud": ["farmacia", "medico", "doctor", "dentista", "analisis", "hospital", "medicamento", "salvavidas"]
```

No hace falta tocar ningun archivo de Python.
