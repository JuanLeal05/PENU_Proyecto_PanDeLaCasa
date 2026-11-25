# 8. Decisiones de arquitectura

Cada decisión importante quedó registrada como un ADR (*Architecture Decision Record*) con el formato del curso: **contexto, alternativas (≥ 2), decisión y consecuencias** (costo, riesgos y trade-offs). Los ADR completos están en el anexo.

| ADR | Pregunta | Decisión | Por qué, en una línea | Autor |
|---|---|---|---|---|
| [ADR-001](../../adr/ADR-001-computo-serverless.md) | ¿Dónde corre la lógica de negocio? | **AWS Lambda** (Python 3.12, ARM64) | Pago por invocación, escala sola al 3x y sin servidores que parchar; ~USD 0 con nuestro volumen frente a ≥ USD 16/mes de solo el balanceador de las alternativas. | Juan |
| [ADR-002](../../adr/ADR-002-dynamodb-transacciones.md) | ¿Qué base de datos? | **DynamoDB on-demand** con transacciones | Las transacciones condicionales resuelven cupo y stock sin locks; $0 en reposo, multi-AZ y PITR sin configurar servidores. | Juan |
| [ADR-003](../../adr/ADR-003-catalogo-estatico.md) | ¿Cómo se sirve el catálogo? | **JSON estático en S3 + CloudFront**, regenerado al editar | Es el tráfico más alto y casi nunca cambia: cero cold starts y costo casi nulo, a cambio de hasta 60 s de desfase. | Juan |
| [ADR-004](../../adr/ADR-004-seguimiento-por-polling.md) | ¿Cómo se informa el estado al cliente? | **Polling cada 20 s** con pausa y parada | Simple y sin estado de conexiones; costo acotado; hasta 20 s de latencia, aceptable para recoger pan. | Juan |
| ADR-005 | ¿Qué tipo de API y cómo se conecta con el front? | **HTTP API directo + CORS** | Más barata que REST API, JWT nativo y throttling por ruta. | Juan Pablo |
| ADR-006 | ¿Cómo se autentica el pipeline y en qué cuenta? | **Cuenta propia + OIDC** | Sin secretos de larga duración y con todos los servicios disponibles. | Juan Pablo |
| ADR-007 | ¿Cómo se define y despliega la infraestructura? | **Terraform + GitHub Actions** | Declarativo, `plan` en cada PR y state remoto con bloqueo. | Juan Pablo |

## Principios que guiaron las decisiones

1. **Pagar solo por uso.** La panadería vende 12 horas al día y su volumen es pequeño: nada que cobre por hora.
2. **La consistencia la da la base de datos.** Las reglas críticas (cupo, stock, estados) se garantizan con condiciones atómicas de DynamoDB, no con código que "revisa y luego escribe".
3. **Lo estático, en el borde.** Lo que casi no cambia (sitio, catálogo, fotos) lo sirve CloudFront; Lambda solo atiende lo dinámico.
4. **Simple antes que sofisticado.** Polling antes que WebSockets, un JSON antes que una caché distribuida: se elige lo que el equipo puede operar y explicar.
5. **Todo verificable.** Contratos escritos antes del código, tests automáticos para cada regla y un pipeline que no deja pasar lo que falla.
