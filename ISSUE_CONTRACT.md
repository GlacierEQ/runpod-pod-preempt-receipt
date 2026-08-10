# Issue contract — Pod Preempt Receipt

## Problem
Spot/preemptible GPU pods die without structured recovery receipts for agents.

## Desired outcome
A bounded, open, testable implementation of **Pod Preempt Receipt** that demonstrates Emit preempt receipts with checkpoint hints and restart grants; refuse silent disappearance.

## Non-goals
- Runpod affiliation or proprietary integration
- Portfolio-wide scale/performance claims
- UI marketing site

## Acceptance
1. Mechanism module implements allow + refuse with structured receipts
2. pytest behavioral suite green
3. operate.py cold-start produces JSON receipt
4. Non-affiliation disclaimer preserved
