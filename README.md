# Instagram Bot Capilar — Guía de instalación

## Qué hace este bot
- Subís hasta 40 fotos de una vez
- La IA (Claude) analiza cada imagen y genera un pie de foto en español para productos capilares
- Las fotos se guardan en una cola y se publican automáticamente en Instagram cada 4 horas
- Podés editar los captions antes de que se publiquen

---

## PASO 1 — Crear cuenta en GitHub y subir el código

1. Entrá a https://github.com y creá una cuenta gratuita
2. Hacé clic en "New repository"
3. Ponele de nombre: `instagram-bot`
4. Dejá todo por defecto y hacé clic en "Create repository"
5. En la pantalla que aparece, hacé clic en "uploading an existing file"
6. Arrastrá los archivos del bot (app.py, requirements.txt, Procfile y la carpeta templates/)
7. Hacé clic en "Commit changes"

---

## PASO 2 — Crear cuenta en Cloudinary (para alojar las imágenes)

1. Entrá a https://cloudinary.com y hacé clic en "Sign up for free"
2. Completá el registro con tu email
3. Una vez adentro, en el panel principal vas a ver una sección llamada "API Keys"
4. Copiá el valor que dice "API Environment variable" — empieza con `cloudinary://...`
   Lo vas a necesitar en el Paso 5.

---

## PASO 3 — Conectar Instagram a Facebook (obligatorio para la API)

1. Abrí Instagram en el celular
2. Ir a tu perfil → tocá las tres rayitas → Configuración → Cuenta
3. Tocá "Cambiar a cuenta profesional" si no lo hiciste ya
4. Ir a Configuración → Cuenta → Página de Facebook vinculada
5. Tocá "Conectar con página de Facebook"
6. Si no tenés página de Facebook, tocá "Crear nueva página" (no la usás para nada, es solo el requisito de Meta)
7. Seguí los pasos y conectá

---

## PASO 4 — Obtener el Access Token y el Account ID de Instagram

1. Entrá a https://developers.facebook.com y hacé clic en "Mis apps" → "Crear app"
2. Elegí "Otro" → "Empresa" → Ponele un nombre cualquiera → Crear
3. En el panel de la app, buscá "Instagram" y hacé clic en "Configurar"
4. Agregá tu cuenta de Instagram en "Cuentas de Instagram"
5. Andá a https://developers.facebook.com/tools/explorer
6. En el selector de app elegí la que creaste
7. Hacé clic en "Generar token de acceso"
8. Marcá estos permisos:
   - instagram_basic
   - instagram_content_publish
   - pages_read_engagement
9. Hacé clic en "Generar token" — copiá ese valor largo (empieza con EAA...)
10. Para obtener tu Instagram Account ID:
    - En el Graph Explorer, en el campo de URL escribí: `me/accounts`
    - Hacé clic en "Ejecutar"
    - Copiá el `id` de tu página de Facebook que aparece
    - Ahora cambiá la URL por: `{el-id-que-copiaste}?fields=instagram_business_account`
    - Hacé clic en "Ejecutar"
    - El número que aparece en `id` dentro de `instagram_business_account` es tu Instagram Account ID

---

## PASO 5 — Subir todo a Railway y configurar las variables

1. Entrá a https://railway.app y hacé clic en "Start a New Project"
2. Elegí "Deploy from GitHub repo"
3. Conectá tu cuenta de GitHub y seleccioná el repositorio `instagram-bot`
4. Railway va a detectar automáticamente que es una app Python
5. Una vez que aparezca el proyecto, hacé clic en él → "Variables"
6. Agregá estas variables una por una (Name → Value):

   | Variable            | Valor                          |
   |---------------------|-------------------------------|
   | ANTHROPIC_API_KEY   | tu clave de Anthropic          |
   | IG_ACCESS_TOKEN     | el token que generaste (EAA...) |
   | IG_ACCOUNT_ID       | tu Instagram Account ID numérico|
   | CLOUDINARY_URL      | cloudinary://... (del Paso 2)  |

7. Hacé clic en "Deploy" — Railway va a instalar todo y arrancar el servidor

---

## PASO 6 — Obtener la URL de tu bot

1. En Railway, hacé clic en tu proyecto → "Settings" → "Domains"
2. Hacé clic en "Generate Domain"
3. Te va a dar una URL del tipo: `https://instagram-bot-production-xxxx.up.railway.app`
4. ¡Esa es tu web! Guardala para usarla cada vez que quieras subir fotos.

---

## Cómo usar el bot día a día

1. Abrí la URL de tu bot en el navegador
2. Arrastrá todas las fotos que quieras programar
3. Esperá a que la IA genere los captions (unos 10-20 segundos por foto)
4. Revisá los captions — si querés cambiar algo, hacé clic en "Editar"
5. Listo. El bot va a publicar automáticamente una foto cada 4 horas.
6. Si querés publicar algo ahora sin esperar, hacé clic en "Publicar ya"

---

## Si algo sale mal

- **El token de Instagram venció:** Los tokens duran ~60 días. Volvé al Graph Explorer y generá uno nuevo. Actualizalo en Railway → Variables.
- **Error al publicar:** Meta a veces rechaza imágenes muy grandes o con ciertos formatos. Probá con otra foto.
- **El bot se detiene:** Railway reinicia el servidor automáticamente, pero la cola se guarda en la base de datos y continúa donde quedó.
