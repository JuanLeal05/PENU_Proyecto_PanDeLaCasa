---
title: "Pan de la Casa — Documento de Diseño de Alto Nivel (HLD)"
subtitle: "Arquitectura cloud serverless en AWS para pedidos web con recogida en tienda"
author:
  - "Juan — aplicación (backend, frontends, HLD)"
  - "Juan Pablo — plataforma (AWS, Terraform, CI/CD, costos)"
date: "27 de noviembre de 2026"
lang: es
---

# Portada

| | |
|---|---|
| **Proyecto** | Pan de la Casa — plataforma web de pedidos para recoger |
| **Curso** | PENU — Escuela Colombiana de Ingeniería Julio Garavito |
| **Integrantes** | Juan (aplicación) · Juan Pablo (plataforma) |
| **Versión** | 1.0 — entrega final |
| **Fecha** | 27 de noviembre de 2026 |
| **Región AWS** | `us-east-1` (CloudFront es global) |
| **Ambientes** | `dev` (despliegue automático) y `prod` (con aprobación manual) |

## Cómo leer este documento

| Sección | Contenido | Autor |
|---|---|---|
| 1 | Contexto del negocio y alcance | Juan |
| 2 | Requisitos y supuestos | Juan |
| 3 | Arquitectura propuesta, flujo de un pedido, concurrencia y cold starts | Juan |
| 4 | Seguridad e identidad | Juan Pablo |
| 5 | Disponibilidad, respaldo y recuperación | Juan Pablo |
| 6 | Observabilidad y operación | Juan Pablo |
| 7 | Riesgos y mitigaciones | Juan |
| 8 | Decisiones de arquitectura (índice de ADR) | Juan |
| Anexo | ADR-001 a ADR-007 completos | Ambos |

Los contratos técnicos que acordamos antes de escribir código (reglas de negocio, API, modelo de datos e integración infraestructura-código) son la fuente de verdad de los detalles; este documento explica el **por qué** de las decisiones.
