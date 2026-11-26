# 1. Contexto del negocio y alcance

## 1.1 El negocio

**Pan de la Casa** es una panadería de barrio en Bogotá. Vende pan fresco que se hornea cada madrugada: lo que no se vende en el día se pierde, y la panadería tiene una capacidad física limitada para alistar pedidos (el personal despacha como máximo unos **10 pedidos cada media hora**).

## 1.2 El problema

Hoy los pedidos llegan por **WhatsApp y por teléfono**:

- El personal interrumpe la atención en el mostrador para contestar, y los pedidos se anotan a mano.
- En las horas pico se forman **filas**, y los clientes que encargaron por mensaje esperan igual que los demás.
- Se **vende pan que ya no hay**: nadie sabe en tiempo real cuánto queda de cada producto.
- No hay forma de saber cuántos pedidos hay comprometidos para cada hora, así que a veces se aceptan más de los que se pueden despachar.
- No hay datos: la panadería no sabe qué se vende más ni a qué hora.

## 1.3 El objetivo

Un sitio web donde el cliente **arma su pedido, elige una franja de 30 minutos para recogerlo y paga en la tienda**, con la **capacidad controlada** por el sistema: nunca se aceptan más de 10 pedidos por franja ni más unidades de las que se hornearon. El personal tiene un **panel** para gestionar los pedidos del día, el catálogo, las fotos, el inventario y ver estadísticas.

Metas medibles:

| Meta | Indicador |
|---|---|
| Cero sobreventa | Ningún pedido aceptado por encima del cupo de la franja o del stock (garantizado por transacciones; ver §3.6) |
| Menos interrupciones en el mostrador | Pedidos web vs. pedidos por WhatsApp/teléfono (estadísticas del panel) |
| Pedidos listos a tiempo | El cliente ve el estado en su celular y llega cuando está "Listo para recoger" |
| Costo bajo | ≤ USD 150/mes en producción (ver resumen de costos, Juan Pablo) |

## 1.4 Actores

| Actor | Quién es | Qué hace en el sistema |
|---|---|---|
| **Cliente** | Vecino del barrio, desde el celular. **Sin cuenta ni login.** | Ve el catálogo y la disponibilidad, hace un pedido para hoy, sigue su estado con un enlace y un código, y puede cancelar mientras esté "Confirmado". |
| **Personal de la panadería (admin)** | 2–3 personas con usuario en Cognito. No hay registro público. | Mueve los pedidos por sus estados, gestiona productos y fotos, ajusta el inventario y consulta estadísticas. |
| **Sistema (jobs programados)** | EventBridge Scheduler | 05:30: restablece el stock a la producción diaria. 18:30: marca como "No recogido" lo que quedó pendiente. |

![Diagrama de contexto (C4 nivel 1)](../diagrams/png/01_contexto_c4.png)

*Figura 1. Contexto del sistema (C4 nivel 1). Diagrama elaborado por Juan Pablo.*

## 1.5 Alcance

**Dentro del alcance**

- Catálogo con fotos, agrupado por categoría, con disponibilidad en tiempo real (agotado / quedan pocas).
- Pedidos **para el mismo día** con recogida en franjas de 30 minutos (07:00 a 17:30), máximo 10 por franja.
- Seguimiento del pedido con enlace + código de 6 caracteres; cancelación por el cliente mientras esté "Confirmado".
- Panel de administración: pedidos por franja y cambio de estado, productos (crear, editar, activar/desactivar, foto), inventario diario y estadísticas.
- Jobs diarios de reinicio de stock y cierre del día.
- Dos ambientes (`dev`, `prod`) desplegados con infraestructura como código y un pipeline CI/CD con aprobación manual a producción.

**Fuera del alcance** (decisiones explícitas, no olvidos)

| Fuera de alcance | Por qué |
|---|---|
| Pagos en línea | Se paga al recoger. Saca PCI-DSS del alcance y evita costos de pasarela. |
| Domicilios | La panadería no tiene repartidores; el modelo es recoger en tienda. |
| Pedidos para días futuros | El producto es pan fresco: el inventario es la producción del día. |
| Cuentas de cliente y fidelización | Fricción innecesaria para un pedido de barrio; menos datos personales que proteger. |
| App móvil nativa | El sitio es responsivo (móvil primero) y no requiere instalación. |
| Notificaciones push / email / SMS | Se usa polling (ADR-004). Queda como mejora futura. |
