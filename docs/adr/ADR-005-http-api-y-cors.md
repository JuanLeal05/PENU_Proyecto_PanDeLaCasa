# ADR-005 · API Gateway HTTP API directo con CORS

- **Estado:** Aceptado
- **Fecha:** 2026-11-25
- **Autor:** Juan Pablo

## Contexto

El frontend del cliente y el panel de administración (servidos desde CloudFront + S3) necesitan consumir 14 rutas REST atendidas por 7 funciones Lambda. Las rutas `/api/admin/*` exigen autenticación mediante tokens JWT emitidos por Amazon Cognito. Debemos elegir el tipo de API Gateway y si se expone directamente o detrás de CloudFront.

## Alternativas

| | REST API (v1) directa | HTTP API (v2) detrás de CloudFront | **HTTP API (v2) directa + CORS** |
|---|---|---|---|
| Costo por millón de peticiones | USD 3,50 | USD 1,00 (+ costo de transferencia CloudFront) | **USD 1,00** (~71 % más barata) |
| Autenticación JWT Cognito | Cognito Authorizer (o Lambda authorizer) | Requiere configurar *Origin Request Policy* para reenviar `Authorization` | **JWT Authorizer nativo** (`iss` + `aud`) sin invocar Lambda |
| Throttling por ruta | Sí (usage plans / stage) | Limitado a nivel de API | **Sí**, `default_route_settings` (20/40) y `POST /api/orders` (5/10) |
| CORS | Configurado en cada método o integración | No necesario (mismo origen) | **Nativo en API Gateway** (`cors_configuration`), sin invocar Lambda en `OPTIONS` |
| WAF directo | Sí (regional WAF en API GW) | Sí (WAF en CloudFront) | No (en esta arquitectura el WAF opcional va en CloudFront) |

## Decisión

Usamos **Amazon API Gateway HTTP API (v2) expuesta directamente por HTTPS**, con **JWT Authorizer** de Cognito para `/api/admin/*` y **CORS** configurado en `aws_apigatewayv2_api` permitiendo únicamente el origen de CloudFront del ambiente (más `http://localhost:5500` en `dev`).

## Consecuencias

**Positivas**
- **Ahorro del 71 %** frente a REST API (USD 1,00 vs USD 3,50 por millón de peticiones).
- **Menor latencia y simplicidad**: el navegador habla directo con API Gateway sin un salto extra por CloudFront ni riesgo de cachear por error respuestas dinámicas de disponibilidad o pedidos.
- **Protección sin costo de cómputo**: el rechazo de tokens inválidos (401), las respuestas `OPTIONS` de CORS y el throttling (429) ocurren en API Gateway sin invocar Lambda.

**Negativas y cómo se mitigan**
- **Preflight `OPTIONS` en mutaciones/admin**: el navegador envía un `OPTIONS` antes de `POST`/`PUT`/`PATCH`/`DELETE` o headers `Authorization`/`Idempotency-Key` → `max_age = 3600` cachea el preflight 1 hora y API Gateway lo responde sin costo de Lambda.
- **Sin WAF directo en HTTP API**: HTTP API no soporta AWS WAF directamente → el WAF opcional se ubica en CloudFront para el sitio web y los assets; la API se protege con throttling estricto (5 req/s en creación de pedidos), validación de esquema y JWT.
