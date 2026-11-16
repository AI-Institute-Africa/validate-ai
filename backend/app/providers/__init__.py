"""Payment-provider adapters: one small class per provider.

Idea from unified-receipt-verifier (MIT): pick the provider from the reference's shape, give every
failure a type, and return a result per item so a batch never drops one silently. Written fresh.

An adapter only knows the SHAPE of its references and, when the provider offers an official API or
webhook, how to ask it. We never scrape a provider's website. With no `transport` the adapter makes
no network call: it can still say "this does not look like an EcoCash reference" (a hint for a
person), and a lookup then fails with `NOT_CONFIGURED`.
"""
