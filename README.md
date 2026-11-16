# Radar de Licitaciones

Panel web con las licitaciones de Mercado Público que calzan con tus filtros: cierres de los próximos 30 días, referencias de precio de lo ya adjudicado, competidores de tu zona y tu cartera de ofertas.

- **GitHub Actions** consulta la API todos los días hábiles y guarda los datos en `data/`. El ticket queda como secreto del repositorio: nunca se publica.
- **GitHub Pages** muestra el panel (`index.html`).
- **Tu cartera** (montos ofertados, costos, socios, notas) se guarda solo en tu navegador. No se sube al repositorio. Usa "Descargar respaldo" para tener una copia o llevarla a otro equipo.

## Puesta en marcha (unos 10 minutos)

1. **Crea el repositorio.** En github.com: *New repository*, con nombre `radar-licitaciones`. Déjalo **público**: GitHub Pages gratis requiere que lo sea. Los datos son públicos de Mercado Público y tu cartera no se sube.
2. **Sube los archivos.** En el repositorio vacío: *uploading an existing file*. Arrastra todo el contenido de esta carpeta, incluida la carpeta `.github` (en Windows, activa "Mostrar elementos ocultos" si no la ves). Haz clic en *Commit changes*.
   - Si la carpeta `.github` no se sube al arrastrarla, créala a mano: *Add file > Create new file*, nombre `.github/workflows/actualizar.yml`, y pega el contenido del archivo.
3. **Guarda el ticket como secreto.** *Settings > Secrets and variables > Actions > New repository secret*. Nombre: `MP_TICKET`. Valor: tu ticket.
4. **Activa la página.** *Settings > Pages*. En *Source* elige *Deploy from a branch*, rama `main`, carpeta `/ (root)`, y guarda. En un par de minutos tendrás la dirección `https://TU-USUARIO.github.io/radar-licitaciones/`.
5. **Primera carga de datos.** Pestaña *Actions > Actualizar datos > Run workflow*. La primera vez revisa 90 días de histórico y puede tardar entre 30 y 90 minutos. Las siguientes son mucho más rápidas. Cuando termine, recarga la página.

Después corre sola de lunes a viernes cerca de las 7:15 de la mañana. También puedes ejecutarla a mano cuando quieras desde *Actions*.

## Ajustar qué vigila

Edita `config.json` desde GitHub (ícono del lápiz):

- `palabras_clave`: se buscan en el nombre de la licitación, sin tildes.
- `excluir`: descarta licitaciones que contengan esas palabras.
- `regiones`: texto parcial de la región del comprador (`"araucan"`). Una lista vacía significa todo Chile.
- `organismos`: opcional, para limitar a ciertos compradores (`"villarrica"`, `"pucon"`).
- `dias_historico`: cuántos días hacia atrás revisa las adjudicaciones.

Los cambios se aplican en la próxima ejecución de la acción.

## Ajustes del panel

Con el botón **Ajustes** (arriba a la derecha) puedes guardar en tu navegador:

- tu ticket, para el botón "Consultar estados en Mercado Público" de la cartera, que consulta en vivo;
- tu RUT y el de tus socios UTP, para que el panel marque como **Ganada** lo adjudicado a ustedes.

## Si la acción falla

- *"Falta el ticket"*: revisa el nombre exacto del secreto, `MP_TICKET`.
- *Error de ticket o de conexión*: si la API rechaza las consultas desde los servidores de GitHub, puedes correr la actualización en tu computador y subir los datos:
  ```
  pip install requests
  set MP_TICKET=tu-ticket
  python scripts/actualizar.py
  ```
  Luego sube la carpeta `data/` al repositorio.
- La acción guarda lo avanzado aunque se corte. La siguiente ejecución continúa donde quedó.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `index.html` | El panel |
| `config.json` | Filtros de vigilancia |
| `scripts/actualizar.py` | Consulta la API y genera los datos |
| `.github/workflows/actualizar.yml` | Programa la ejecución diaria |
| `data/licitaciones.json` | Datos para el panel (se genera solo) |
| `data/estado.json` | Días ya revisados y licitaciones descartadas (se genera solo) |
