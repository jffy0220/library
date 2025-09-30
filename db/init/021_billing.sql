-- Schema objects that support the billing subsystem.
CREATE TABLE IF NOT EXISTS billing_purchase_intents (
  id BIGSERIAL PRIMARY KEY,
  intent_id TEXT NOT NULL UNIQUE,
  customer_type TEXT NOT NULL CHECK (customer_type IN ('user', 'organization')),
  customer_id TEXT NOT NULL,
  plan_key TEXT NOT NULL,
  billing_interval TEXT NOT NULL CHECK (billing_interval IN ('monthly', 'annual')),
  seat_quantity INTEGER NOT NULL CHECK (seat_quantity >= 1),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'expired', 'canceled')),
  provider_session_id TEXT NULL,
  provider_session_url TEXT NULL,
  return_url TEXT NULL,
  cancel_url TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  expires_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS billing_purchase_intents_provider_session_idx
  ON billing_purchase_intents(provider_session_id)
  WHERE provider_session_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS billing_subscriptions (
  id BIGSERIAL PRIMARY KEY,
  subscription_id TEXT NOT NULL UNIQUE,
  provider_id TEXT NOT NULL,
  customer_type TEXT NOT NULL CHECK (customer_type IN ('user', 'organization')),
  customer_id TEXT NOT NULL,
  plan_key TEXT NOT NULL,
  billing_interval TEXT NOT NULL CHECK (billing_interval IN ('monthly', 'annual')),
  status TEXT NOT NULL CHECK (status IN ('active', 'canceled', 'past_due')),
  seat_quantity INTEGER NOT NULL CHECK (seat_quantity >= 1),
  current_period_start TIMESTAMPTZ NULL,
  current_period_end TIMESTAMPTZ NULL,
  trial_end TIMESTAMPTZ NULL,
  cancel_at TIMESTAMPTZ NULL,
  canceled_at TIMESTAMPTZ NULL,
  grace_period_expires_at TIMESTAMPTZ NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS billing_subscriptions_customer_idx
  ON billing_subscriptions(customer_type, customer_id);

CREATE TABLE IF NOT EXISTS billing_invoices (
  id BIGSERIAL PRIMARY KEY,
  invoice_id TEXT NOT NULL UNIQUE,
  subscription_id TEXT NOT NULL REFERENCES billing_subscriptions(subscription_id) ON DELETE CASCADE,
  amount_due BIGINT NOT NULL CHECK (amount_due >= 0),
  currency TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'paid', 'void', 'uncollectible', 'past_due')),
  period_start TIMESTAMPTZ NULL,
  period_end TIMESTAMPTZ NULL,
  provider_invoice_id TEXT NULL,
  pdf_url TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS billing_invoices_subscription_idx
  ON billing_invoices(subscription_id, created_at DESC);

CREATE TABLE IF NOT EXISTS billing_webhook_events (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS billing_webhook_events_type_idx
  ON billing_webhook_events(event_type, received_at DESC);

CREATE OR REPLACE FUNCTION set_billing_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_billing_purchase_intents_updated ON billing_purchase_intents;
CREATE TRIGGER trg_billing_purchase_intents_updated
  BEFORE UPDATE ON billing_purchase_intents
  FOR EACH ROW
  EXECUTE FUNCTION set_billing_timestamp();

DROP TRIGGER IF EXISTS trg_billing_subscriptions_updated ON billing_subscriptions;
CREATE TRIGGER trg_billing_subscriptions_updated
  BEFORE UPDATE ON billing_subscriptions
  FOR EACH ROW
  EXECUTE FUNCTION set_billing_timestamp();

DROP TRIGGER IF EXISTS trg_billing_invoices_updated ON billing_invoices;
CREATE TRIGGER trg_billing_invoices_updated
  BEFORE UPDATE ON billing_invoices
  FOR EACH ROW
  EXECUTE FUNCTION set_billing_timestamp();