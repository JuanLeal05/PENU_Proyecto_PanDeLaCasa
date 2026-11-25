# ADR-003 · Catálogo como JSON estático en S3 + CloudFront

- **Estado:** Aceptado
- **Fecha:** 2026-11-24
- **Autor:** Juan

## Contexto

El catálogo (nombre, descripción, categoría, precio y foto de ~40 productos) es lo **primero que carga cada visita** y, por lejos, el contenido más pedido: ~1.080 sesiones/día el fin de semana. En cambio, **casi nunca cambia**: el personal edita un precio o una foto unas pocas veces por semana.

Lo que sí cambia minuto a minuto es el **stock** y los **cupos**, y esos necesitan estar al día.

## Alternativas

| | Lambda `GET /catalog` sin caché | Lambda `GET /catalog` con caché (en memoria o en API Gateway) | **JSON estático en S3 + CloudFront, regenerado al editar** |
|---|---|---|---|
| Invocaciones de Lambda | Una por visita | Menos, pero la caché por entorno se pierde con cada cold start; la caché de API Gateway solo existe en REST API y cobra por hora | **Cero** |
| Latencia | Cold start + Scan de DynamoDB | Variable | Servido desde el borde de CloudFront (ms) |
| Costo | Lambda + DynamoDB por visita | Igual o caché con costo fijo | Solicitudes de CloudFront (centavos) |
| Frescura | Inmediata | Según TTL | ≤ 60 s tras editar |
| Complejidad | Baja | Media (invalidación) | Baja: se regenera en cada escritura |

## Decisión

El catálogo es un archivo **`assets/catalog/catalog.json`** en el bucket de assets, servido por CloudFront con `Cache-Control: max-age=60`:

- La Lambda `admin-products` lo **regenera en cada escritura de producto** (crear, editar, activar/desactivar, cambiar foto), leyendo la tabla con lectura consistente.
- Incluye **solo productos activos** y **no incluye stock**: el stock y los cupos vienen de `GET /api/availability`, que el front pide **en paralelo** con el catálogo.
- Las imágenes tienen nombre único (`assets/images/<productId>/<uuid>.webp`), así que se pueden cachear sin invalidaciones.
- El script de datos semilla puede publicar el primer catálogo (`--publish-catalog`).

## Consecuencias

**Positivas**

- **El tráfico más alto no toca Lambda ni DynamoDB**: cero cold starts para ver el catálogo y costo casi nulo.
- El catálogo carga desde el borde de CloudFront, lo que mejora la primera impresión en el celular.
- Separar catálogo (casi estático) de disponibilidad (dinámica) deja a Lambda solo lo que de verdad cambia.

**Negativas y cómo se mitigan**

- **Hasta 60 s de desfase** tras editar un producto → aceptable para una panadería; el panel le avisa al personal ("se verá en el catálogo en ≤ 60 s").
- **Un precio viejo en pantalla** durante esos segundos → no tiene efecto económico: **el precio cobrado siempre sale de la base de datos** al crear el pedido, nunca del cliente.
- **Dos peticiones en vez de una** al abrir el sitio → van en paralelo y la del catálogo sale del CDN.
- **La Lambda de productos necesita escribir en S3** → permiso `s3:PutObject` acotado a `assets/*` del bucket de assets.
