# Generar imagen de una ruta (Era Hiboria)

Cuando el usuario pida «la ruta de A a B» (o una imagen de ella), generar un PNG con el mapa, los hexágonos usados y el desglose. No hace falta publicar ni crear artefactos salvo que lo pida.

## Archivos del proyecto
- `claude/rutas-hiboria.html`: datos (hexágonos, terreno, 214 nodos), mapa, red de ciudades y reglas incrustados. Es también la página con selector de origen, destino, paradas, exclusiones y casilla de red de ciudades.
- `claude/rutas.py`: script que lee ese HTML, calcula la ruta y dibuja el PNG.

## Pasos
1. `project_read` de `claude/rutas-hiboria.html` y de `claude/rutas.py`. Al ser grande, la herramienta guarda el HTML en un archivo local y devuelve su ruta. El script llega como texto: guardarlo como `rutas.py`.
2. Ver nombres válidos si hay dudas: `python3 rutas.py RUTA_HTML --lista` (formato `Ciudad | Reino`). Admite coincidencia parcial sin tildes si es única.
3. Generar: `python3 rutas.py RUTA_HTML salida.png ORIGEN DESTINO [--paradas "A,B"] [--evitar "Ghaza,Argos"] [--sin-mar] [--sin-red] [--embarque DIAS]`
   - Hasta 5 paradas intermedias obligatorias, en orden.
   - **Por defecto usa la red de ciudades vecinas y permite el mar.**
   - `--sin-red`: ruta directa hex a hex (la más corta posible, sin pasar por ciudades vecinas).
   - `--sin-mar`: fuerza solo tierra.
   - `--embarque`: días extra por cada salida a mar (por defecto 0).
   - `--evitar`: ciudades y/o países separados por comas (ver abajo).
4. Enviar el PNG al usuario (SendUserFile) y dar el total de días en una línea. Si el script avisa de «ciudad alcanzable más cercana», decírselo.

## Red de ciudades vecinas (modo por defecto)
- La ruta se calcula entre ciudades «vecinas», no directamente: se enlazan las ciudades a menos de 14 días entre sí por tierra (el coste es direccional: cuenta el hexágono de llegada, no el de salida), más los enlaces por mar.
- Una ciudad aislada se conecta con su vecina más cercana. Hay 10 «enlaces puente» (hasta 32 días, p. ej. Issedon–Shaulan) para que la red por tierra sea una sola.
- Con la red, el total suele ser igual o algo mayor que en ruta directa (p. ej. Venzia → Aghrapur: 87 d con red, 79,3 d directa).
- Con exclusiones, cada conexión afectada se recalcula esquivando lo evitado. Si no hay ruta hasta el destino, el script llega a la ciudad alcanzable más cercana (en línea recta) y lo avisa en consola y en el panel. Esto solo ocurre en modo red.

## Exclusiones (--evitar)
- Ciudad: se bloquea su hexágono y no se puede usar como puerto ni como parada intermedia.
- País: se bloquean sus ciudades y todos los hexágonos de tierra ininterrumpidos del mismo color de relleno que sus ciudades en el mapa original. Es una aproximación: reinos vecinos con el mismo color se bloquean juntos (el script lo avisa en la imagen, p. ej. Koth arrastra Khauran y Khoraja).
- El mar sigue permitido al evitar un país: los barcos pueden navegar por sus costas, pero no parar en sus puertos.
- Origen, destino y paradas no pueden estar dentro de lo evitado (el script avisa).
- En la imagen, el territorio evitado sale sombreado en gris.

## Qué dibuja
Mapa recortado a la ruta con hexágonos rojos (tierra) y morados (mar y acceso a puerto), marcadores A/B y paradas numeradas, y un panel con total de días, días por tipo de terreno y desglose por tramo (cada tramo es una conexión entre ciudades vecinas).

## Reglas del modelo (por si hay que explicarlas)
- Hexágono de 30 millas de vértice a vértice (lado 15 millas, 25,98 millas entre centros, ≈ 585 mi²; ≈ 48 km, 42 km y ≈ 1.515 km²). Un día de camino en llanura = 1 hexágono ≈ 26 millas (42 km). Mar: 3 hexágonos/día.
- Millas estimadas = hexágonos recorridos × 26 (25,98) (tierra, mar y total); en kilómetros, × 1,609344. La imagen (por defecto millas, `--km` para kilómetros) y la página (interruptor millas/kilómetros) las muestran junto a los días. Es una estimación: no cuenta rodeos dentro del hexágono.
- Tierra, días por hexágono: llanura 1; desierto, colinas, pantano, bosque y tundra 2; montaña y jungla 3. El agua no se cruza a pie. Los ríos y los caminos no están modelados.
- Los barcos solo paran en ciudades costeras e islas (no atraviesan puertos ni islas).
- Terreno actualizado el 23/11/2026: se quitaron las colinas manuales del centro de Shem (ahora llanura) y se añadieron bosque y tundra (Pictland y Marcas Bossonianas pasan de jungla a bosque; Khitai pasa de jungla a bosque salvo «Lost Jungle»; bosques parciales en Aquilonia, Nemedia, Zingara, Gunderland, Pedassa, Koth y Colchian; tundra y taiga en el norte).
- Resultados de referencia: Venzia → Aghrapur 79,3 d directa / 87 d red; Asgalun ↔ Akbitana 37,7 d; Akbitana → Asgalun evitando Estigia 42,3 d (por Akkharia, Buryat, Ghaza y Kyros, y mar hasta Asgalun); Lireigh → Brutheim 51 d directa (tundra y taiga cuestan 2 d).

## Si falla
- Falta Pillow o numpy: `pip install pillow numpy --break-system-packages`.
- Si el HTML leído llega truncado, volver a leerlo; debe contener `<script id="data"`, `<script id="edges"` y `data:image/jpeg;base64`. Sin `edges` el script avisa y usa ruta directa.
