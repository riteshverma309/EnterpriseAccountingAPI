"""
app/services/invoicing_service.py
Service layer for Invoicing, Billing, and Party management.
"""
import uuid
from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.invoicing import Party, Invoice, InvoiceLine, InvoiceStatus, InvoiceType
from app.models.ledger import Account, Tenant
from app.schemas.invoicing import PartyCreate, InvoiceCreate
from app.schemas.ledger import JournalEntryCreate, JournalLineCreate
from app.services.ledger_service import post_journal_entry, TenantNotFoundError


class PartyNotFoundError(Exception):
    def __init__(self, party_id: str):
        super().__init__(f"Party {party_id!r} not found.")


class InvoiceNotFoundError(Exception):
    def __init__(self, invoice_id: str):
        super().__init__(f"Invoice {invoice_id!r} not found.")


class InvoiceAlreadyPostedError(Exception):
    def __init__(self, invoice_id: str):
        super().__init__(f"Invoice {invoice_id!r} is already posted.")


# ── Parties ───────────────────────────────────────────────────────────────────

def create_party(db: Session, payload: PartyCreate) -> Party:
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    party = Party(
        tenant_id=payload.tenant_id,
        name=payload.name,
        party_type=payload.party_type,
        email=payload.email,
        phone=payload.phone,
    )
    db.add(party)
    db.commit()
    db.refresh(party)
    return party


def list_parties(db: Session, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[Party]:
    return db.execute(
        select(Party).where(Party.tenant_id == tenant_id).offset(skip).limit(limit)
    ).scalars().all()


# ── Invoices ──────────────────────────────────────────────────────────────────

def create_invoice(db: Session, payload: InvoiceCreate) -> Invoice:
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    party = db.get(Party, payload.party_id)
    if not party or party.tenant_id != payload.tenant_id:
        raise PartyNotFoundError(str(payload.party_id))

    invoice = Invoice(
        tenant_id=payload.tenant_id,
        party_id=payload.party_id,
        invoice_type=payload.invoice_type,
        invoice_number=payload.invoice_number,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        currency=payload.currency.upper(),
        notes=payload.notes,
        status=InvoiceStatus.DRAFT
    )
    db.add(invoice)
    db.flush()

    for line in payload.lines:
        inv_line = InvoiceLine(
            invoice_id=invoice.id,
            account_id=line.account_id,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax_amount=line.tax_amount,
        )
        db.add(inv_line)

    db.commit()
    db.refresh(invoice)
    return invoice


def post_invoice(db: Session, invoice_id: uuid.UUID, ar_ap_account_id: uuid.UUID) -> Invoice:
    """
    Post an invoice to the ledger.
    This creates a balancing JournalEntry.
    For RECEIVABLE (AR): Debit AR Account, Credit Revenue/Tax Accounts.
    For PAYABLE (AP): Credit AP Account, Debit Expense/Tax Accounts.
    """
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise InvoiceNotFoundError(str(invoice_id))

    if invoice.status != InvoiceStatus.DRAFT:
        raise InvoiceAlreadyPostedError(str(invoice_id))

    total_amount = sum(line.line_total for line in invoice.lines)
    
    # Construct Journal Lines
    j_lines = []
    
    if invoice.invoice_type == InvoiceType.RECEIVABLE:
        # AR: Debit AR account for total amount
        j_lines.append(
            JournalLineCreate(
                account_id=ar_ap_account_id,
                amount=total_amount,  # Positive = Debit
                description=f"AR for Invoice {invoice.invoice_number}"
            )
        )
        # Revenue: Credit (Negative)
        for line in invoice.lines:
            j_lines.append(
                JournalLineCreate(
                    account_id=line.account_id,
                    amount=-line.line_total, # Negative = Credit
                    description=line.description
                )
            )
    else:
        # AP: Credit AP account for total amount
        j_lines.append(
            JournalLineCreate(
                account_id=ar_ap_account_id,
                amount=-total_amount,  # Negative = Credit
                description=f"AP for Bill {invoice.invoice_number}"
            )
        )
        # Expense: Debit (Positive)
        for line in invoice.lines:
            j_lines.append(
                JournalLineCreate(
                    account_id=line.account_id,
                    amount=line.line_total, # Positive = Debit
                    description=line.description
                )
            )

    journal_entry_payload = JournalEntryCreate(
        tenant_id=invoice.tenant_id,
        description=f"Posting {'Invoice' if invoice.invoice_type == InvoiceType.RECEIVABLE else 'Bill'} {invoice.invoice_number}",
        reference_id=invoice.invoice_number,
        currency=invoice.currency,
        lines=j_lines
    )

    # Re-use ledger service to post journal entry (this validates double-entry)
    entry = post_journal_entry(db, journal_entry_payload)

    invoice.status = InvoiceStatus.POSTED
    invoice.journal_entry_id = entry.id
    db.commit()
    db.refresh(invoice)

    return invoice


def list_invoices(db: Session, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[Invoice]:
    return db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant_id).order_by(Invoice.issue_date.desc()).offset(skip).limit(limit)
    ).scalars().unique().all()
