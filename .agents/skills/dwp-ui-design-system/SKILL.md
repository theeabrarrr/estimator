---
name: dwp-ui-design-system
description: Standard UI/UX design system and layout guidelines for DWP Field Assistant Engine. Enforces max 4-color palette, progressive step-by-step disclosure, non-congested card layouts, and interactive category selection.
---

# DWP Field Assistant UI/UX Design System

This skill defines the authoritative design system and layout principles for all UI modules in the **DWP Field Assistant Engine** (`estimator`). Any agent modifying or extending the interface MUST strictly follow these rules.

---

## 🎨 1. Strict 4-Color Palette Rule
To eliminate visual clutter and ensure an enterprise-grade, clean interface, **no more than 4 primary colors** may be used across the application:

1. **Primary Navy Blue (`#0369A1` / `#1E3A8A`)**: Used for main titles, key section headers, active tab highlights, and primary buttons.
2. **Dark Slate (`#0F172A`)**: Primary text color, heavy subheadings, and net totals.
3. **Light Slate (`#F8FAFC`)**: Card background fills, container surfaces, and section backgrounds.
4. **Sky Accent (`#0284C7`)**: Secondary action buttons, interactive badges, selection indicators, and key amounts.

*Neutral borders & dividers (`#E2E8F0` / `#CBD5E1`) may be used for card separation.*

---

## 📐 2. Layout Structure & Progressive Disclosure
Avoid congested multi-column views, dense text blocks, or overwhelming tables. Structure the user journey using **progressive step-by-step disclosure**:

### Step 1: Model Selection Header
- Clean, prominent dropdown for selecting the equipment model.
- Displays unit metadata (brand, tonnage, category) cleanly in a single line.

### Step 2: Category & Sub-Assembly Explorer
- Instead of showing all spare parts in a long cluttered list at once, group parts by **Category / Sub-Assembly** (e.g., *Outdoor Inverter PCB*, *Evaporator Assembly*, *Valves*, *Sensors*).
- Clicking/selecting a category dynamically filters and expands the compatible spare parts list underneath.

### Step 3: Interactive Cart & Selected Parts Container
- Selected spare parts are shown in a clean, non-congested summary chip container.
- Each item has an explicit remove action without cluttering the main browsing grid.

### Step 4: Base Overheads & Service Charges
- Simple horizontal control row for **Visit Charges**, **Mobility/Labour Charges**, and **Refrigerant Gas Refill**.
- Warranty status selector (`Cash`, `Under Warranty`, `Partial Warranty`) cleanly integrated below overheads.

### Step 5: Real-Time Official Estimate & WhatsApp Output
- High-contrast, clean summary card presenting itemized cost breakdown.
- Copyable, pre-formatted WhatsApp quotation output with direct chat launch button.

---

## 🚀 3. Quality Verification & Strict GitHub Push Workflow
- All UI modifications must be verified for responsiveness and clean rendering before declaring completion.
- **Mandatory Git Push**: Every change must be committed with a descriptive git message and pushed to GitHub immediately.
