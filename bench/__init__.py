"""RDTII-Bench — the measured half of VeriTrade, run as a Ledger tenant.

Nothing in here is part of the product pipeline. These modules exist so that a
claim about retrieval can be *measured* rather than argued about, and so that
every number printed in the paper traces back to a run record on disk.

The rule the whole repo runs on applies here too: a number is carried from a
recorded run, never typed. `bench` therefore imports the shipped code under test
(`backend.pipeline.retrieval._tok`, `backend.rdtii`) rather than reimplementing
it -- a benchmark that measures a copy of the tokeniser measures nothing.
"""
