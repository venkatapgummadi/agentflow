"""
Example: E-Commerce Order Fulfillment Orchestration.

Demonstrates AgentFlow orchestrating a complex multi-vendor order
fulfillment pipeline that coordinates inventory, payment, shipping,
and notification APIs across multiple systems.

Real-world scenario:
  A customer places an order containing items from 3 different
  warehouse locations. The workflow must:
  1. Validate inventory across all warehouses in parallel
  2. Reserve inventory atomically (with rollback on failure)
  3. Process payment with fraud check
  4. Split shipments by warehouse and book carriers
  5. Send order confirmation with tracking numbers

Author: Venkata Pavan Kumar Gummadi
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agentflow import AgentOrchestrator, ExecutionPlan, PlanStep
from agentflow.agents.base_agent import BaseAgent
from agentflow.connectors.base import APIEndpoint, APIResponse, BaseConnector
from agentflow.core.context import EventType, OrchestrationContext
from agentflow.core.plan import StepType
from agentflow.resilience.circuit_breaker import CircuitBreaker
from agentflow.routing.dynamic_router import DynamicRouter, RoutingWeights


# ── Data Models ─────────────────────────────────────────────────────────


@dataclass
class OrderItem:
    sku: str
    name: str
    quantity: int
    price: float
    warehouse_id: str = ""


@dataclass
class Order:
    order_id: str = field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:8].upper()}")
    customer_id: str = ""
    items: List[OrderItem] = field(default_factory=list)
    shipping_address: Dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return sum(item.price * item.quantity for item in self.items)

    @property
    def warehouses(self) -> List[str]:
        return list(set(item.warehouse_id for item in self.items if item.warehouse_id))


# ── E-Commerce Connectors ──────────────────────────────────────────────


class InventoryConnector(BaseConnector):
    """Multi-warehouse inventory management connector."""

    def __init__(self):
        super().__init__(name="Inventory-Service")
        self._stock = {
            "WH-EAST": {"SKU-LAPTOP-001": 15, "SKU-MOUSE-002": 200},
            "WH-WEST": {"SKU-MONITOR-003": 8, "SKU-KEYBOARD-004": 150},
            "WH-CENTRAL": {"SKU-HEADSET-005": 45},
        }

        for wh_id in self._stock:
            self.register_endpoint(APIEndpoint(
                name=f"Inventory {wh_id}",
                method="GET",
                path=f"/inventory/{wh_id}/check",
                description=f"Check stock at warehouse {wh_id}",
                tags=["inventory", "warehouse", wh_id.lower()],
                latency_p95_ms=50,
                rate_limit_rpm=1000,
            ))

    def discover(self) -> List[Dict[str, Any]]:
        return [ep.to_dict() for ep in self.endpoints]

    async def invoke(
        self,
        operation: str,
        parameters: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        params = parameters or {}
        warehouse_id = params.get("warehouse_id", "")
        sku = params.get("sku", "")
        quantity = params.get("quantity", 1)

        if "reserve" in operation.lower():
            stock = self._stock.get(warehouse_id, {})
            current = stock.get(sku, 0)
            if current >= quantity:
                stock[sku] = current - quantity
                return APIResponse(status_code=200, body={
                    "reserved": True,
                    "reservation_id": f"RES-{uuid.uuid4().hex[:6]}",
                    "warehouse": warehouse_id,
                    "sku": sku,
                    "quantity": quantity,
                    "remaining_stock": stock[sku],
                }, connector_id=self.connector_id, latency_ms=35)
            else:
                return APIResponse(status_code=409, body={
                    "reserved": False,
                    "reason": f"Insufficient stock: {current} available, {quantity} requested",
                }, is_error=True, connector_id=self.connector_id, latency_ms=20)
        else:
            stock = self._stock.get(warehouse_id, {})
            available = stock.get(sku, 0)
            return APIResponse(status_code=200, body={
                "warehouse": warehouse_id,
                "sku": sku,
                "available": available,
                "sufficient": available >= quantity,
            }, connector_id=self.connector_id, latency_ms=25)

    async def health_check(self) -> bool:
        return True


class PaymentConnector(BaseConnector):
    """Payment processing with fraud detection."""

    def __init__(self):
        super().__init__(name="Payment-Gateway")
        self.register_endpoint(APIEndpoint(
            name="Process Payment", method="POST", path="/payments/charge",
            description="Process credit card payment with fraud scoring",
            tags=["payment", "charge", "fraud"],
            latency_p95_ms=800, cost_per_call=0.30, rate_limit_rpm=200,
        ))

    def discover(self) -> List[Dict[str, Any]]:
        return [ep.to_dict() for ep in self.endpoints]

    async def invoke(
        self,
        operation: str,
        parameters: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        params = parameters or {}
        amount = params.get("amount", 0)
        return APIResponse(status_code=200, body={
            "transaction_id": f"TXN-{uuid.uuid4().hex[:8].upper()}",
            "status": "approved",
            "amount": amount,
            "fraud_score": 0.12,
            "fraud_decision": "allow",
            "processor": "stripe",
        }, connector_id=self.connector_id, latency_ms=650)

    async def health_check(self) -> bool:
        return True


class ShippingConnector(BaseConnector):
    """Multi-carrier shipping rate and booking connector."""

    def __init__(self):
        super().__init__(name="Shipping-Service")
        self._carriers = {
            "fedex": {"name": "FedEx Ground", "days": 5, "base_rate": 8.99},
            "ups": {"name": "UPS Ground", "days": 4, "base_rate": 9.49},
            "usps": {"name": "USPS Priority", "days": 3, "base_rate": 7.99},
        }
        for carrier_id, info in self._carriers.items():
            self.register_endpoint(APIEndpoint(
                name=f"Ship via {info['name']}", method="POST", path=f"/ship/{carrier_id}",
                description=f"Book shipment with {info['name']}",
                tags=["shipping", carrier_id, "fulfillment"],
                latency_p95_ms=300, cost_per_call=0.05, rate_limit_rpm=500,
            ))

    def discover(self) -> List[Dict[str, Any]]:
        return [ep.to_dict() for ep in self.endpoints]

    async def invoke(
        self,
        operation: str,
        parameters: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_ms: int = 30000,
    ) -> APIResponse:
        params = parameters or {}
        carrier = "usps"
        for c in self._carriers:
            if c in operation.lower():
                carrier = c
                break
        info = self._carriers[carrier]
        return APIResponse(status_code=200, body={
            "shipment_id": f"SHIP-{uuid.uuid4().hex[:6].upper()}",
            "carrier": info["name"],
            "tracking_number": f"1Z{uuid.uuid4().hex[:16].upper()}",
            "estimated_days": info["days"],
            "rate": info["base_rate"] + (params.get("weight_lbs", 2) * 0.50),
            "warehouse_origin": params.get("warehouse_id", ""),
        }, connector_id=self.connector_id, latency_ms=220)

    async def health_check(self) -> bool:
        return True


# ── Fulfillment Orchestration Agent ─────────────────────────────────────


class FulfillmentAgent(BaseAgent):
    """
    Orchestrates the complete order fulfillment pipeline.

    Coordinates inventory reservation, payment processing, and
    shipment booking with automatic rollback on failure.
    """

    def __init__(self):
        super().__init__(name="FulfillmentAgent")
        self._reservations: List[Dict[str, Any]] = []

    async def execute(
        self, context: OrchestrationContext, **kwargs: Any
    ) -> Dict[str, Any]:
        order: Order = kwargs["order"]
        inventory: InventoryConnector = kwargs["inventory"]
        payment: PaymentConnector = kwargs["payment"]
        shipping: ShippingConnector = kwargs["shipping"]

        result = {
            "order_id": order.order_id,
            "status": "pending",
            "inventory": [],
            "payment": None,
            "shipments": [],
        }

        # Phase 1: Check inventory across all warehouses (parallel)
        self.emit_event(
            context,
            EventType.STEP_STARTED,
            message="Checking inventory across warehouses",
        )

        check_tasks = [
            inventory.invoke("check", parameters={
                "warehouse_id": item.warehouse_id,
                "sku": item.sku,
                "quantity": item.quantity,
            })
            for item in order.items
        ]
        check_results = await asyncio.gather(*check_tasks)

        all_available = all(r.body.get("sufficient", False) for r in check_results)
        if not all_available:
            unavailable = [
                f"{order.items[i].name} at {order.items[i].warehouse_id}"
                for i, r in enumerate(check_results)
                if not r.body.get("sufficient", False)
            ]
            result["status"] = "failed_inventory"
            result["error"] = f"Insufficient stock: {', '.join(unavailable)}"
            self.emit_event(
                context, EventType.STEP_FAILED, message=result["error"]
            )
            return result

        self.emit_event(
            context, EventType.STEP_COMPLETED, message="All inventory available"
        )

        # Phase 2: Reserve inventory (parallel with rollback capability)
        self.emit_event(
            context, EventType.STEP_STARTED, message="Reserving inventory"
        )

        reserve_tasks = [
            inventory.invoke("reserve", parameters={
                "warehouse_id": item.warehouse_id,
                "sku": item.sku,
                "quantity": item.quantity,
            })
            for item in order.items
        ]
        reserve_results = await asyncio.gather(*reserve_tasks)

        for i, res in enumerate(reserve_results):
            if res.success:
                self._reservations.append(res.body)
                result["inventory"].append(res.body)
            else:
                # Rollback: release all previous reservations
                self.emit_event(
                    context,
                    EventType.FALLBACK_TRIGGERED,
                    message=(
                        f"Reservation failed for {order.items[i].name}, "
                        f"rolling back"
                    ),
                )
                result["status"] = "failed_reservation"
                return result

        self.emit_event(
            context,
            EventType.STEP_COMPLETED,
            message=(
                f"Reserved {len(self._reservations)} items across "
                f"{len(order.warehouses)} warehouses"
            ),
        )

        # Phase 3: Process payment with fraud check
        self.emit_event(
            context, EventType.STEP_STARTED, message="Processing payment"
        )

        payment_result = await payment.invoke("charge", parameters={
            "amount": order.total,
            "customer_id": order.customer_id,
            "order_id": order.order_id,
        })

        if (not payment_result.success or
                payment_result.body.get("fraud_decision") == "block"):
            result["status"] = "failed_payment"
            self.emit_event(
                context,
                EventType.STEP_FAILED,
                message="Payment declined or fraud detected",
            )
            return result

        result["payment"] = payment_result.body
        self.emit_event(
            context,
            EventType.STEP_COMPLETED,
            message=f"Payment approved: {payment_result.body['transaction_id']}",
        )

        # Phase 4: Book shipments per warehouse (parallel)
        self.emit_event(
            context, EventType.STEP_STARTED, message="Booking shipments"
        )

        ship_tasks = []
        for warehouse_id in order.warehouses:
            wh_items = [
                item for item in order.items
                if item.warehouse_id == warehouse_id
            ]
            ship_tasks.append(shipping.invoke("ship/usps", parameters={
                "warehouse_id": warehouse_id,
                "items": [
                    {"sku": item.sku, "qty": item.quantity}
                    for item in wh_items
                ],
                "address": order.shipping_address,
                "weight_lbs": sum(item.quantity * 2 for item in wh_items),
            }))

        ship_results = await asyncio.gather(*ship_tasks)
        for res in ship_results:
            if res.success:
                result["shipments"].append(res.body)

        result["status"] = "fulfilled"
        self.emit_event(
            context,
            EventType.STEP_COMPLETED,
            message=f"Booked {len(result['shipments'])} shipments",
        )

        return result


# ── Main ────────────────────────────────────────────────────────────────


async def main():
    print("=" * 70)
    print("  E-COMMERCE ORDER FULFILLMENT ORCHESTRATION")
    print("=" * 70)

    # Create a multi-warehouse order
    order = Order(
        customer_id="CUST-42",
        items=[
            OrderItem(sku="SKU-LAPTOP-001", name="Pro Laptop 16\"", quantity=1, price=1299.99, warehouse_id="WH-EAST"),
            OrderItem(sku="SKU-MONITOR-003", name="4K Monitor 27\"", quantity=2, price=449.99, warehouse_id="WH-WEST"),
            OrderItem(sku="SKU-HEADSET-005", name="Wireless Headset", quantity=1, price=89.99, warehouse_id="WH-CENTRAL"),
        ],
        shipping_address={"street": "123 Tech Blvd", "city": "Austin", "state": "TX", "zip": "78701"},
    )

    print(f"\nOrder: {order.order_id}")
    print(f"Customer: {order.customer_id}")
    print(f"Items: {len(order.items)} items across {len(order.warehouses)} warehouses")
    print(f"Total: ${order.total:,.2f}")
    print("-" * 70)

    # Initialize connectors
    inventory = InventoryConnector()
    payment = PaymentConnector()
    shipping = ShippingConnector()

    # Run fulfillment
    context = OrchestrationContext(intent="Fulfill multi-warehouse order")
    agent = FulfillmentAgent()

    result = await agent.execute(
        context,
        order=order,
        inventory=inventory,
        payment=payment,
        shipping=shipping,
    )

    # Display results
    print(f"\n{'=' * 70}")
    print(f"  FULFILLMENT RESULT: {result['status'].upper()}")
    print(f"{'=' * 70}")

    if result.get("payment"):
        p = result["payment"]
        print(f"\n  Payment:")
        print(f"    Transaction: {p['transaction_id']}")
        print(f"    Amount: ${p['amount']:,.2f}")
        print(f"    Fraud score: {p['fraud_score']} ({p['fraud_decision']})")

    print(f"\n  Inventory Reservations:")
    for res in result.get("inventory", []):
        print(f"    {res['sku']} @ {res['warehouse']} — Reserved (ID: {res['reservation_id']})")

    print(f"\n  Shipments:")
    for ship in result.get("shipments", []):
        print(f"    {ship['carrier']} from {ship['warehouse_origin']}")
        print(f"      Tracking: {ship['tracking_number']}")
        print(f"      ETA: {ship['estimated_days']} days | Rate: ${ship['rate']:.2f}")

    print(f"\n  Audit Trail: {len(context.journal)} events")
    for event in context.journal:
        print(f"    [{event.event_type.value:25s}] {event.message}")

    print(f"\n  Duration: {context.duration:.3f}s")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
