# Rutas de la Era Hiboria

Calculadora de días y kilómetros de viaje para campañas de *Conan: La Era Hiboria* (Monolith), sobre un mapa de hexágonos de 30 km (vértice a vértice).

- **Página web:** `index.html`. Elige origen, destino, hasta 5 paradas, ciudades o países a evitar y si se viaja por mar. Muestra el recorrido sobre el mapa, los días por tipo de terreno y los km.
- **Script:** `rutas.py`. Hace lo mismo desde la terminal y guarda una imagen PNG con la ruta.
- **Tablas:** `docs/` (distancias entre ciudades por tierra y mar, localizaciones).

## Usar la página

Abre `index.html` en el navegador (no necesita servidor ni internet). Para tenerla en la web, ver «Publicar con GitHub Pages».

La casilla **Red de ciudades vecinas** calcula la ruta saltando entre ciudades cercanas; sin ella, la ruta es directa hexágono a hexágono.

## Usar el script

Requiere Python 3 con Pillow y numpy: `pip install pillow numpy`.

```
python3 rutas.py index.html ruta.png ORIGEN DESTINO [--paradas "A,B"] [--evitar "Ghaza,Argos"] [--sin-mar] [--sin-red] [--embarque DIAS]
python3 rutas.py index.html --lista      # nombres válidos (Ciudad | Reino)
```

Por defecto usa la red de ciudades vecinas y permite el mar. Ejemplo:

```
python3 rutas.py index.html ruta.png Akbitana Asgalun --evitar Estigia
# 42,3 dias, ~1.221 km
```

Los nombres admiten coincidencia parcial y sin tildes si es única.

## Reglas del modelo

- Hexágono de 30 km vértice a vértice: lado 15 km, 25,98 km entre centros, ≈ 585 km².
- Tierra, días por hexágono al que se entra: llanura 1; desierto, colinas, pantano, bosque y tundra 2; montaña y jungla 3. El agua no se cruza a pie. Los ríos y los caminos no están modelados.
- Mar: 3 hexágonos al día. Los barcos solo paran en ciudades costeras e islas.
- Kilómetros estimados = hexágonos recorridos × 26 (25,98).
- Red de ciudades: se enlazan las ciudades a menos de 14 días por tierra (coste direccional), más enlaces por mar y 10 «enlaces puente» para que la red sea una sola.
- Evitar un país bloquea sus ciudades y los hexágonos de tierra contiguos del mismo color en el mapa (aproximación: reinos vecinos del mismo color se bloquean juntos). El mar sigue permitido.
- Si con las exclusiones no hay ruta, en modo red se llega a la ciudad alcanzable más cercana al destino y se avisa.

## Publicar con GitHub Pages

1. Sube el contenido de esta carpeta a un repositorio nuevo (rama `main`).
2. En el repositorio: **Settings → Pages → Build and deployment → Source: Deploy from a branch**, rama `main`, carpeta `/ (root)`.
3. En un minuto la página estará en `https://TU-USUARIO.github.io/NOMBRE-DEL-REPO/`.

## Estructura

```
LICENSE         licencia MIT del código
LICENSE-docs    licencia CC BY-NC-SA 4.0 de docs/
index.html      página (datos, mapa y red de ciudades incrustados)
rutas.py        script que genera la imagen de la ruta
docs/           tablas de distancias, rutas marítimas, localizaciones e instrucciones
```

## Licencia

- Código (`rutas.py` y la lógica de `index.html`): MIT, ver `LICENSE`.
- Tablas y textos de `docs/`: CC BY-NC-SA 4.0, ver `LICENSE-docs`.
- El mapa incrustado en `index.html` queda excluido de ambas licencias.

## Aviso

El mapa incrustado en `index.html` es el mapa de Hiboria de Conan; sus derechos pertenecen a sus titulares. Úsalo en privado o para tu mesa de juego y revisa los derechos antes de hacer público el repositorio.
