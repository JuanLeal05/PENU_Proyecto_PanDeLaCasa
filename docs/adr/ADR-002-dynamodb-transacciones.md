# ADR-002 · DynamoDB on-demand con transacciones condicionales

- **Estado:** Aceptado
- **Fecha:** 2026-11-24
- **Autor:** Juan

## Contexto

El corazón del negocio es **no vender lo que no hay**: máximo 10 pedidos por franja de 30 minutos y nunca más unidades que las horneadas. Varios clientes pueden pedir lo último **al mismo tiempo**, y crear un pedido toca varias cosas a la vez (cupo de la franja, stock de cada producto, el pedido y la clave de idempotencia). Además:

- Los patrones de acceso son pocos y conocidos de antemano: por clave (pedido, producto), "pedidos de un día ordenados por franja" y "franjas de hoy".
- Requisitos: RPO 24 h / RTO 4 h, 99,5 % de disponibilidad, costo bajo y tráfico intermitente.

## Alternativas

| | RDS PostgreSQL `db.t4g.micro` | Aurora Serverless v2 | **DynamoDB on-demand** |
|---|---|---|---|
| Consistencia del cupo | `SELECT … FOR UPDATE` o `UPDATE … WHERE count < 10` dentro de una transacción SQL | Igual que RDS | `TransactWriteItems` con `ConditionExpression` (todo o nada) |
| Costo fijo mensual | ≈ USD 12 de instancia + almacenamiento; **el doble** en Multi-AZ | ≈ USD 43/mes con el mínimo de 0,5 ACU; con auto-pausa (0 ACU) hay segundos de reanudación en la primera petición | **USD 0** en reposo; se paga por solicitud (centavos con nuestro volumen) |
| Disponibilidad | Multi-AZ opcional (y pagado) | Multi-AZ configurable | Multi-AZ incluido |
| Respaldo | Snapshots automáticos | Snapshots automáticos | **PITR**: restauración a cualquier segundo de los últimos 35 días |
| Red y operación | VPC, security groups, conexiones (las Lambdas necesitarían VPC o RDS Proxy) | Igual | API HTTPS con IAM: **sin VPC** ni manejo de conexiones |
| Consultas ad hoc | SQL libre | SQL libre | Limitadas a claves e índices |

## Decisión

Usamos **DynamoDB en modo on-demand** con cuatro tablas (`products`, `orders` con el GSI `byDate`, `slots`, `idempotency`) y **transacciones condicionales**:

- **Crear pedido** = una sola `TransactWriteItems`: incrementar el contador de la franja si `count < 10`, descontar el stock de cada producto si `stock >= qty AND active = true`, insertar el pedido y la clave de idempotencia si no existen.
- **Cancelar** = la transacción inversa, con condición sobre el estado actual del pedido.
- **Cambiar de estado** = `UpdateItem` con condición sobre el estado actual (dos administradores no se pisan).
- El motivo exacto de un rechazo se lee de `CancellationReasons` (posición 0 = franja; 1..n = productos).

PITR activado en `orders` y `products`; TTL en `slots` (7 días) e `idempotency` (24 h).

## Consecuencias

**Positivas**

- **Cero sobreventa sin locks ni colas**: DynamoDB serializa las transacciones; la perdedora recibe un error claro (`SLOT_FULL`, `OUT_OF_STOCK`) y no deja nada a medias. Está cubierto por tests de carrera con `moto`.
- **Costo en reposo de USD 0** y sin capacidad que dimensionar; multi-AZ incluido.
- **RPO de minutos** con PITR, muy por encima del RPO de 24 h exigido.
- Las Lambdas **no necesitan VPC** (menos cold start, sin NAT ni RDS Proxy).

**Negativas y cómo se mitigan**

- **Consultas ad hoc limitadas** → diseñamos el modelo desde los patrones de acceso: el GSI `byDate` (`pickupDate` + `slotKey = "<franja>#<createdAt>"`) da los pedidos del día ya ordenados; las estadísticas se agregan en memoria (≤ 220 pedidos/día).
- **Las transacciones cuestan el doble** de unidades de escritura → con ~2.760 pedidos/mes son centavos.
- **Palabras reservadas** (`count`, `date`, `status`) → siempre con `ExpressionAttributeNames`.
- **Modelado menos familiar que SQL** para el equipo → el contrato de datos fija tablas, claves y la matriz IAM, y los tests crean las tablas idénticas al contrato para detectar desalineaciones con Terraform.
