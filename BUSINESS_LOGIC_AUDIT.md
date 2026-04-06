# Business Logic & Workflow Audit
**Project:** Car Rental Enterprise (Django)
**Audit Date:** 2026-04-03
**Scope:** Live code only — operation logic, status transitions, workflow completeness, side effects, missing guards, missing state updates, accounting/posting steps, deletion/edit protection, unsafe actions, missing related-object updates.

---

## Summary Table

| ID | Severity | Group | Description |
|----|----------|-------|-------------|
| BL-001 | 🔴 Critical | Missing status update | Rental cancellation does not reset vehicle status |
| BL-002 | 🔴 Critical | Wrong workflow | Traffic fine journal entry uses wrong `source_id` |
| BL-003 | 🔴 Critical | Broken code | `payments/services.py::process_deposit_refund` crashes at runtime |
| BL-004 | 🟠 High | Missing guard | `Payment.clean()` allows payments on completed rentals |
| BL-005 | 🟠 High | Missing guard | Payment cap includes deposit — double-collection risk |
| BL-006 | 🟠 High | Missing status update | `Deposit.status` never stored as PARTIALLY_REFUNDED / FULLY_REFUNDED |
| BL-007 | 🟠 High | Incomplete workflow | `create_monthly_renewal()` leaves old rental perpetually active/overdue |
| BL-008 | 🟡 Medium | Incomplete workflow | `create_monthly_renewal()` does not copy deposit_amount, damage_fees, other_charges |
| BL-009 | 🟡 Medium | Missing guard | `create_monthly_renewal()` has no posted/paid guard on old rental |
| BL-010 | 🟡 Medium | Duplicate path | Two conflicting `post_deposit_receipt` functions (legacy vs new) |
| BL-011 | 🟢 Low | Dead code | Duplicate `formfield_for_foreignkey` method in RentalAdmin — first is silently dead |

---

## Detailed Findings

---

### BL-001 — 🔴 CRITICAL: Rental Cancellation Does Not Reset Vehicle Status

**File:** `apps/rentals/models.py` — `Rental.save()`
**Lines:** 662–679

**Problem:**
When a rental transitions from `active` → `cancelled`, the vehicle status is never reset from `rented` back to `available`. The vehicle becomes permanently stuck in `rented` state.

**Evidence:**

In `Rental.save()`, the vehicle-update block only runs when `status == "active"`:
```python
if locked_vehicle:
    if self.status == "active":   # ← only enters this branch for active
        if locked_vehicle.status != "rented":
            ...
            locked_vehicle.status = "rented"
            locked_vehicle.save(update_fields=["status"])
```
There is no `elif self.status == "cancelled"` branch to set the vehicle back to `available`.

The `return_vehicle()` method does set vehicle to `available`, but that method only runs when the button is pressed on an active rental — it explicitly rejects cancelled rentals:
```python
if locked_rental.status == "cancelled":
    raise ValidationError("Cancelled rentals cannot be returned.")
```

The `post_delete` signal does reset vehicle status, but only when the rental is **deleted**, not cancelled.

The admin blocks deletion of completed/cancelled rentals:
```python
def has_delete_permission(self, request, obj=None):
    if obj and obj.status in ('completed', 'cancelled'):
        return False
```

**Net effect:** User cancels an active rental via the admin status dropdown → rental is saved as `cancelled` → vehicle remains `rented` → vehicle is invisible to all "available vehicles" queries → vehicle is stuck and cannot be rented again without a manual database fix.

**Fix direction:** In `Rental.save()`, add a branch for the `active → cancelled` transition that sets `locked_vehicle.status = "available"` and saves.

---

### BL-002 — 🔴 CRITICAL: Traffic Fine Journal Entry Uses Rental ID as source_id Instead of Fine ID

**File:** `apps/accounting/services.py` — `post_rental_revenue()`
**Lines:** 482–504, 522–523

**Problem:**
The journal entry created for the traffic fine recognition uses `source_id=locked_rental.id` (the rental's primary key) instead of the TrafficFine record's primary key. The TrafficFine record is created *after* the journal entry, making correct linking impossible at creation time.

**Evidence:**

Step 1 — journal entry created with rental ID:
```python
if traffic_fines_amount > Decimal("0.00"):
    create_journal_entry(
        ...
        source_app="traffic_fines",
        source_model="TrafficFine",
        source_id=locked_rental.id,   # ← THIS IS THE RENTAL'S PK, NOT THE FINE'S PK
        ...
    )
```

Step 2 — TrafficFine record created after:
```python
if traffic_fines_amount > Decimal("0.00"):
    create_traffic_fine_from_rental(rental=locked_rental)
```

The resulting `JournalEntry` row has `source_app="traffic_fines"`, `source_model="TrafficFine"`, `source_id=<rental_pk>`. Any audit or reporting code that queries `JournalEntry.objects.filter(source_model="TrafficFine", source_id=fine.pk)` will find nothing. The journal entry for a fine points to the wrong record.

Additionally, the `TrafficFine` model has its own `customer_collection_journal_entry` and `government_payment_journal_entry` fields for subsequent steps, but no field for the initial recognition entry — that link is effectively broken.

**Fix direction:** Create the TrafficFine record first (or find the existing one), then pass `source_id=traffic_fine.id` to `create_journal_entry`.

---

### BL-003 — 🔴 CRITICAL: `payments/services.py::process_deposit_refund` Crashes at Runtime

**File:** `apps/payments/services.py` — `process_deposit_refund()`
**Lines:** 14–61

**Problem:**
This function accepts a `DepositRefund` instance but treats it as if it has a direct `rental` ForeignKey. `DepositRefund` has no such field — it only has `deposit` → `Deposit` → `Rental`. The function will raise `AttributeError` immediately on any call.

**Evidence:**

Line 24 — accesses `refund_instance.rental` which does not exist on `DepositRefund`:
```python
locked_rental = (
    type(refund_instance.rental)           # ← AttributeError: DepositRefund has no 'rental'
    .objects.select_for_update()
    .get(pk=refund_instance.rental_id)     # ← also doesn't exist
)
```

Line 43 — same wrong assumption:
```python
DepositRefund.objects.filter(rental_id=refund_instance.rental_id)  # ← DepositRefund has no rental_id
```

The correct function is in `apps/deposits/services.py::process_deposit_refund()`, which correctly traverses `refund.deposit.rental`. This function in `payments/services.py` appears to be a copy-paste error from an earlier design where DepositRefund had a direct rental FK.

**Risk:** If any code path calls `payments.services.process_deposit_refund`, it crashes with an unhandled `AttributeError`. Even if currently unreachable (dead), it is a maintenance trap — any future refactor that wires it will cause a silent runtime crash.

**Fix direction:** Either delete this function entirely (the correct one is in `deposits/services.py`) or fix the field traversal path.

---

### BL-004 — 🟠 HIGH: `Payment.clean()` Allows Payments on Completed Rentals

**File:** `apps/payments/models.py` — `Payment.clean()`
**Lines:** 176–179

**Problem:**
The validation only blocks payments on cancelled rentals. Payments on completed (returned) rentals are silently allowed. The code comment directly contradicts this behavior.

**Evidence:**

The comment says:
```python
# في نظامنا الحالي:
# لا نسمح بإنشاء دفعة على عقد مكتمل أو ملغي
# (In our current system: we don't allow creating a payment on completed or cancelled rentals)
```

But the code only blocks cancelled:
```python
if rental_status in ("cancelled",):     # ← "completed" is missing from this tuple
    errors["rental"] = (
        "Cannot create a payment for a cancelled rental."
    )
```

**Impact:** A user can add payments to a completed rental via the admin inline or the API endpoint (`api_rentals_list_create` / `api_rental_detail`). This affects financial reporting — payments attached to closed contracts will be counted but the rental revenue may already be posted, leading to double-counting or unreconciled balances.

**Fix direction:** Change the condition to `if rental_status in ("cancelled", "completed"):`.

---

### BL-005 — 🟠 HIGH: Payment Cap Includes Deposit — Double-Collection Risk

**File:** `apps/rentals/models.py` — `_calculate_net_total()` and `apps/payments/models.py` — `Payment.clean()`
**Lines:** rentals/models.py 355–372, payments/models.py 204–221

**Problem:**
`net_total` is calculated as: `(days × rate) + tax + traffic_fines + damage_fees + other_charges + deposit_amount`. The `Payment.clean()` and `process_payment()` cap total payments at `rental.net_total`. This means payments can be taken for the full amount including the deposit through the Payment system, while the deposit also has its own independent collection path through the Deposit model.

**Evidence:**

`_calculate_net_total()` includes deposit:
```python
return (
    subtotal + tax_amount + traffic_fines + damage_fees + other_charges + deposit_amount
).quantize(Decimal("0.01"))
```

`Payment.clean()` caps at `rental.net_total` (which includes deposit):
```python
if new_total > rental_total:
    ...
```

The admin's **Collect Contract & Deposit** button correctly handles this by only collecting `net_total - deposit - fines` through the Payment system, then collecting deposit separately via the Deposit system.

However, a user who creates payments manually through the admin inline or the API can add payments up to the full `net_total` (which includes the deposit amount), and also separately collect the deposit via the Deposit admin. The system will not detect the over-collection because the two totals are tracked in separate tables.

**Fix direction:** Either subtract `deposit_amount` and `traffic_fines` from the cap in payment validation, or enforce that the deposit/fine payment paths are the only valid ones for those amounts (block manual payments that exceed the rental-only portion).

---

### BL-006 — 🟠 HIGH: `Deposit.status` Is Never Stored as PARTIALLY_REFUNDED or FULLY_REFUNDED

**File:** `apps/deposits/services.py` — `post_deposit_refund()`
**Lines:** 283–292

**Problem:**
`DepositStatus` defines four statuses: `PENDING_COLLECTION`, `RECEIVED`, `PARTIALLY_REFUNDED`, `FULLY_REFUNDED`. The `Deposit` model has a `calculated_status` property that correctly computes these. But after a refund is posted, `post_deposit_refund()` only sets `status` back to `RECEIVED` or `PENDING_COLLECTION` — never to `PARTIALLY_REFUNDED` or `FULLY_REFUNDED`.

**Evidence:**

After posting a refund, the stored status is set as:
```python
new_status = (
    DepositStatus.RECEIVED
    if locked_deposit.journal_entry_id
    else DepositStatus.PENDING_COLLECTION
)
Deposit.objects.filter(pk=locked_deposit.pk).update(status=new_status)
```

The `PARTIALLY_REFUNDED` and `FULLY_REFUNDED` values in `DepositStatus` are never written to the database by any service.

**Impact:** Any query/filter on `Deposit.objects.filter(status=DepositStatus.PARTIALLY_REFUNDED)` will always return zero rows. The admin sidebar filter on status, any report that groups deposits by status, and any business logic that checks `deposit.status == FULLY_REFUNDED` will be wrong. The `calculated_status` property gives the right answer but only for single-object display — it can't be used in querysets.

**Fix direction:** Replace the new_status calculation with one that uses `calculated_status` logic: if `remaining_amount <= 0`, use `FULLY_REFUNDED`; if `refunded_amount > 0`, use `PARTIALLY_REFUNDED`; otherwise `RECEIVED`.

---

### BL-007 — 🟠 HIGH: `create_monthly_renewal()` Leaves the Old Rental Perpetually Active and Overdue

**File:** `apps/rentals/models.py` — `create_monthly_renewal()`
**Lines:** 776–827

**Problem:**
When a monthly renewal is triggered, `create_monthly_renewal()` creates a new rental starting the day after the old one's `end_date`. It does **not** close or complete the old rental. The old rental remains `status="active"` with `actual_return_date=None`, and since its `end_date` has now passed, it will immediately show as **Overdue** in every report and filter.

**Evidence:**

The method creates the new rental but makes no changes to the current (`self`) rental:
```python
new_rental = Rental.objects.create(
    customer=self.customer,
    vehicle=self.vehicle,
    ...
)

RentalLog.objects.create(
    rental=self,
    action="Rental Renewed",
    ...
)

return new_rental
# self.status is still "active", self.actual_return_date is still None
```

After renewal, the system will show two active rentals on the same vehicle — both visible in the "active" and "overdue" dashboard counts. The old rental will accumulate overdue days indefinitely.

**Fix direction:** Inside `create_monthly_renewal()`, after creating the new rental, call `self.return_vehicle()` on the old rental (or directly update its status/actual_return_date) to close it cleanly before returning.

---

### BL-008 — 🟡 MEDIUM: `create_monthly_renewal()` Does Not Copy deposit_amount, damage_fees, or other_charges

**File:** `apps/rentals/models.py` — `create_monthly_renewal()`
**Lines:** 800–812

**Problem:**
The renewal only copies a subset of the old rental's financial fields. Three fields default to `0` in the new contract:
- `deposit_amount` — new rental has no deposit even if original had one
- `damage_fees` — new rental starts clean
- `other_charges` — new rental starts clean

**Evidence:**

```python
new_rental = Rental.objects.create(
    customer=self.customer,
    vehicle=self.vehicle,
    branch=self.branch,
    status='active',
    start_date=next_start,
    end_date=next_end,
    daily_rate=self.daily_rate,
    vat_percentage=self.vat_percentage,
    traffic_fines=Decimal('0.00'),   # explicitly zeroed
    auto_renew=self.auto_renew,
    created_by=user or self.created_by,
    # deposit_amount, damage_fees, other_charges not passed → default 0
)
```

Whether deposit_amount should carry over to renewals is a business decision. But the current behavior means: a customer who paid a deposit on their original contract will have no deposit required for renewals, and the system will not track it as a liability for the renewed period.

**Fix direction:** Explicitly pass `deposit_amount=self.deposit_amount` in the create call (and decide whether damage_fees/other_charges should carry over or always start at zero).

---

### BL-009 — 🟡 MEDIUM: `create_monthly_renewal()` Has No Guard on Old Rental Posting or Payment Status

**File:** `apps/rentals/models.py` — `create_monthly_renewal()`
**Lines:** 776–827

**Problem:**
`create_monthly_renewal()` only checks `if not self.auto_renew`. It does not check whether:
1. The old rental has been posted to accounting (`accounting_state == "posted"`)
2. The old rental has been paid (`remaining_amount == 0`)

**Impact:** A renewal can be triggered on an unposted, unpaid rental. The new rental immediately creates another financial obligation while the original obligation is still unrecorded in accounting. Repeated renewals on an unposted rental could create a long chain of unaccounted contracts.

**Fix direction:** Add guards:
```python
if self.accounting_state != "posted":
    raise ValidationError("Cannot renew an unposted rental.")
```

---

### BL-010 — 🟡 MEDIUM: Two Conflicting `post_deposit_receipt` Functions Exist

**Files:**
- `apps/accounting/services.py` lines 718–775 — accepts `rental` object
- `apps/deposits/services.py` lines 48–114 — accepts `Deposit` object

**Problem:**
There are two functions named `post_deposit_receipt` doing the same job through different paths. The one in `accounting/services.py` is a legacy version that works directly off the rental's `deposit_amount` field and updates `rental.deposit_journal_entry`. The one in `deposits/services.py` is the newer, correct version that works off the `Deposit` model and updates both `Deposit.journal_entry` and `Deposit.status`.

**Evidence:**

`accounting/services.py` version:
```python
def post_deposit_receipt(*, rental):          # ← takes a rental
    ...
    Rental.objects.filter(pk=locked_rental.pk, deposit_journal_entry__isnull=True).update(
        deposit_journal_entry=entry,
    )
    # Does NOT update the Deposit record at all
```

`deposits/services.py` version:
```python
def post_deposit_receipt(*, deposit: Deposit):   # ← takes a Deposit
    ...
    Deposit.objects.filter(pk=..., journal_entry__isnull=True).update(
        journal_entry=entry,
        status=DepositStatus.RECEIVED,
    )
    Rental.objects.filter(pk=locked_deposit.rental_id).update(
        deposit_journal_entry=entry,
    )
    # Updates BOTH Deposit and Rental
```

The admin correctly imports from `deposits.services`. But `accounting/services.py` exports its version too, and any code importing `from apps.accounting.services import post_deposit_receipt` will silently use the legacy version, bypassing the Deposit model update.

**Fix direction:** Remove or clearly mark as deprecated the `post_deposit_receipt` function in `accounting/services.py`. Any caller should import from `deposits.services` exclusively.

---

### BL-011 — 🟢 LOW: Duplicate `formfield_for_foreignkey` Method in RentalAdmin — First Is Silently Dead

**File:** `apps/rentals/admin.py`
**Lines:** 375–394 (dead), 589–612 (live)

**Problem:**
`RentalAdmin` defines `formfield_for_foreignkey` twice. Python silently overwrites the first definition with the second. The first definition (lines 375–394) is unreachable dead code.

**Evidence:**

First definition at line 375:
```python
def formfield_for_foreignkey(self, db_field, request, **kwargs):
    if db_field.name == 'vehicle':
        obj_id = request.resolver_match.kwargs.get('object_id')
        ...
```

Second definition at line 589 (this is the one that runs):
```python
def formfield_for_foreignkey(self, db_field, request, **kwargs):
    if db_field.name == "vehicle":
        object_id = request.resolver_match.kwargs.get("object_id")
        ...
```

The two implementations are functionally equivalent, making this a low-risk duplication. However, it creates a maintenance burden — edits to one copy will be silently ignored. Any future developer debugging vehicle dropdown behavior may look at the first definition and make changes that have no effect.

**Fix direction:** Delete lines 375–394 (the first definition).

---

## Cross-Cutting Notes

**Status inconsistency pattern:** Three separate places maintain status fields that can diverge from computed reality — `Rental.status` vs `Rental.is_overdue`, `Deposit.status` vs `Deposit.calculated_status`, and the TrafficFine status vs its journal entries. The pattern works for display but breaks for filtering/reporting. Consider a periodic sync job or enforce writes through services that always keep stored status in sync.

**net_total recalculation on every save():** `Rental.save()` calls `recalculate_totals()` unconditionally. If `daily_rate` is changed on an active (unposted) rental, `net_total` updates correctly. But if the rental is already posted and `daily_rate` is edited (possible because posted rentals don't lock `daily_rate` until status is completed/cancelled), the journal entry is for the old amount while `net_total` reflects the new one. The `accounting_state` of the rental would remain "posted" but the amounts diverge. Consider locking `daily_rate`, `vat_percentage`, `deposit_amount`, `traffic_fines`, `damage_fees`, and `other_charges` as soon as `accounting_state == "posted"` rather than waiting for status to be completed/cancelled.
