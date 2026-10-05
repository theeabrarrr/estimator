---
name: dwp-ui-design-system
description: Standard UI/UX design system and layout guidelines for DWP Field Assistant Engine. Enforces pure #FFFFFF (White) & #000000 (Black) high-contrast color palette, dark mode compatibility, typography hierarchy, progressive step-by-step disclosure, and clean card styling.
---

# DWP Field Assistant UI/UX Design System

This skill defines the authoritative design system, typography guidelines, and layout principles for all UI modules in the **DWP Field Assistant Engine** (`estimator`). Any agent modifying or extending the interface MUST strictly follow these rules.

---

## 🎨 1. Strict High-Contrast Color Palette (#FFFFFF & #000000)
The user interface is built strictly around a **pure high-contrast monochrome color palette**:

1. **Pure White (`#FFFFFF`)**: Primary light background, surface fill, and dark-mode high-contrast text color.
2. **Pure Black (`#000000`)**: Primary dark background, high-contrast light-mode text color, borders, and main title headers.
3. **Adaptive CSS Variables (`var(--text-color)`, `var(--secondary-background-color)`)**: Every custom container, card, badge, table cell, and step box MUST use adaptive CSS variables or theme classes so that colors adapt automatically in both **Light Mode** and **Dark Mode**.

### Dark Mode & Light Mode Contract:
- **Light Mode:** `#FFFFFF` background, `#000000` crisp black typography, neutral borders (`rgba(0,0,0,0.15)`).
- **Dark Mode:** `#000000` / `#0E1117` dark background, `#FFFFFF` crisp white typography, neutral borders (`rgba(255,255,255,0.2)`).
- **Zero Text Overlapping:** Never hardcode fixed dark text (`#0F172A`, `#1E3A8A`) inside containers without dark mode overrides. All text elements MUST inherit adaptive theme variables to prevent contrast clashing or overlapping.

---

## ✒️ 2. Typography & Visual Hierarchy
- **Main App Title:** `font-size: 1.5rem; font-weight: 800; color: var(--text-color);`
- **Sub-titles & Captions:** `font-size: 0.85rem; opacity: 0.8; color: var(--text-color);`
- **Step Headers (`.dwp-step-title`):** `font-weight: 700; font-size: 1.0rem; color: var(--text-color);`
- **Part Descriptions:** `font-weight: 700; font-size: 0.96rem; color: var(--text-color);`
- **Prices & Totals:** `font-weight: 800; font-size: 1.05rem; color: var(--text-color);`

---

## 📐 3. Progressive Step-by-Step Layout Flow
Avoid congested multi-column views. Always present the workflow in a 4-step progressive disclosure flow:

- **Step 1: Appliance Model Selection** (`selected_model` dropdown).
- **Step 2: Sub-Assembly Category Explorer & Selected Cart** (Category selectbox using `format_func` to preserve exact string keys, top floating cart summary).
- **Step 3: Base Overheads & Service Charges** (Visit Charges, Mobility/Labour, Refrigerant Gas Refill, Warranty selector).
- **Step 4: Real-Time Official Estimate & WhatsApp Generator** (Itemized estimate table and copyable WhatsApp quotation box).

---

## 🚀 4. Quality Verification & Strict GitHub Push Protocol
- Test interface across both **Light Mode** and **Dark Mode** to ensure zero text color clashing or layout distortion.
- **Mandatory Git Push**: Every change must be committed with a descriptive git message and pushed to GitHub immediately.
