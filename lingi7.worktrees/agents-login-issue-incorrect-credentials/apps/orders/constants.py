"""
Order lifecycle constants for Lingi7.

State machine mirrors the escrow state machine to ensure funds
are never released without a corresponding order state transition.
"""

# ─────────────────────────────── Order States ────────────────────────────────

class OrderStatus:
    """
    7-state order lifecycle.

    DRAFT → PENDING_PAYMENT → PAYMENT_RECEIVED → PROCESSING
        → SHIPPED → DELIVERED → COMPLETED
                 ↘ DISPUTED (from PROCESSING / SHIPPED / DELIVERED)
                 ↘ CANCELLED (from DRAFT / PENDING_PAYMENT)
                 ↘ REFUNDED  (from DISPUTED / terminal resolution)
    """
    DRAFT              = "DRAFT"               # Order created, not yet submitted
    PENDING_PAYMENT    = "PENDING_PAYMENT"     # Submitted, awaiting escrow hold
    PAYMENT_RECEIVED   = "PAYMENT_RECEIVED"    # Escrow hold confirmed
    PROCESSING         = "PROCESSING"          # Seller acknowledged, packing
    SHIPPED            = "SHIPPED"             # Dispatch confirmed with tracking
    DELIVERED          = "DELIVERED"           # Buyer confirmed receipt
    COMPLETED          = "COMPLETED"           # Escrow released to seller
    DISPUTED           = "DISPUTED"            # Active dispute raised
    CANCELLED          = "CANCELLED"           # Order voided pre-fulfilment
    REFUNDED           = "REFUNDED"            # Funds returned to buyer

    CHOICES = [
        (DRAFT,           "Draft"),
        (PENDING_PAYMENT, "Pending Payment"),
        (PAYMENT_RECEIVED,"Payment Received"),
        (PROCESSING,      "Processing"),
        (SHIPPED,         "Shipped"),
        (DELIVERED,       "Delivered"),
        (COMPLETED,       "Completed"),
        (DISPUTED,        "Disputed"),
        (CANCELLED,       "Cancelled"),
        (REFUNDED,        "Refunded"),
    ]

    # States from which escrow release is valid
    ESCROW_RELEASABLE = {DELIVERED, COMPLETED}

    # Terminal states — no further transitions
    TERMINAL = {COMPLETED, CANCELLED, REFUNDED}

    # States allowing buyer-initiated cancellation
    CANCELLABLE_BY_BUYER = {DRAFT, PENDING_PAYMENT}

    # States allowing admin cancellation
    CANCELLABLE_BY_ADMIN = {DRAFT, PENDING_PAYMENT, PAYMENT_RECEIVED, PROCESSING}


# ─────────────────────────────── Allowed Transitions ─────────────────────────

ORDER_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.DRAFT:             {OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED},
    OrderStatus.PENDING_PAYMENT:   {OrderStatus.PAYMENT_RECEIVED, OrderStatus.CANCELLED},
    OrderStatus.PAYMENT_RECEIVED:  {OrderStatus.PROCESSING, OrderStatus.DISPUTED, OrderStatus.CANCELLED},
    OrderStatus.PROCESSING:        {OrderStatus.SHIPPED, OrderStatus.DISPUTED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED:           {OrderStatus.DELIVERED, OrderStatus.DISPUTED},
    OrderStatus.DELIVERED:         {OrderStatus.COMPLETED, OrderStatus.DISPUTED},
    OrderStatus.DISPUTED:          {OrderStatus.COMPLETED, OrderStatus.REFUNDED},
    OrderStatus.COMPLETED:         set(),   # terminal
    OrderStatus.CANCELLED:         set(),   # terminal
    OrderStatus.REFUNDED:          set(),   # terminal
}


# ─────────────────────────────── Fulfilment Types ────────────────────────────

class FulfilmentType:
    STANDARD_DELIVERY  = "STANDARD_DELIVERY"    # Carrier delivery
    PICKUP             = "PICKUP"               # Buyer collection from seller
    DIGITAL            = "DIGITAL"              # Digital goods / download link

    CHOICES = [
        (STANDARD_DELIVERY, "Standard Delivery"),
        (PICKUP,            "Pickup"),
        (DIGITAL,           "Digital"),
    ]


# ─────────────────────────────── Dispute Reasons ─────────────────────────────

class DisputeReason:
    ITEM_NOT_RECEIVED   = "ITEM_NOT_RECEIVED"
    ITEM_NOT_AS_DESC    = "ITEM_NOT_AS_DESCRIBED"
    WRONG_ITEM          = "WRONG_ITEM"
    DAMAGED_ITEM        = "DAMAGED_ITEM"
    SELLER_UNRESPONSIVE = "SELLER_UNRESPONSIVE"
    OTHER               = "OTHER"

    CHOICES = [
        (ITEM_NOT_RECEIVED,   "Item Not Received"),
        (ITEM_NOT_AS_DESC,    "Item Not As Described"),
        (WRONG_ITEM,          "Wrong Item Sent"),
        (DAMAGED_ITEM,        "Item Arrived Damaged"),
        (SELLER_UNRESPONSIVE, "Seller Unresponsive"),
        (OTHER,               "Other"),
    ]


# ─────────────────────────────── Dispute Resolution ──────────────────────────

class DisputeResolution:
    REFUND_BUYER  = "REFUND_BUYER"
    RELEASE_SELLER = "RELEASE_SELLER"
    PARTIAL_REFUND = "PARTIAL_REFUND"

    CHOICES = [
        (REFUND_BUYER,    "Full Refund to Buyer"),
        (RELEASE_SELLER,  "Release Funds to Seller"),
        (PARTIAL_REFUND,  "Partial Refund"),
    ]
